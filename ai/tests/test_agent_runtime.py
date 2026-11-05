import pytest
from pydantic import BaseModel, ValidationError
from ai.agents.contracts import AgentDefinition, AgentContext, AgentResult, AgentStatus
class Output(BaseModel):
    value: int

def definition(**kw):
    return AgentDefinition(name='test', description='Test', system_prompt='Test', output_schema=Output, **kw)

def test_contracts():
    assert definition().limits.max_steps == 8
    assert AgentContext(request_id='r', input_data={}).request_id == 'r'
    for data in ({'request_id':'', 'input_data':{}}, {'request_id':'r'}):
        with pytest.raises(ValidationError): AgentContext(**data)
    with pytest.raises(ValidationError): definition(limits={'max_steps':0})
    with pytest.raises(ValidationError): AgentResult(status=AgentStatus.FAILED)
    with pytest.raises(ValidationError): AgentResult(status=AgentStatus.SUCCESS, pending_fields=['x'])
import asyncio
from ai.agents.tools import ToolDefinition, ToolRegistry, ToolExecutor

def test_tools():
    async def check():
        registry = ToolRegistry()
        tool = ToolDefinition(name='echo', description='Echo', input_schema=Output, output_schema=Output, handler=lambda v:v)
        registry.register(tool)
        assert registry.lookup('echo') is tool and len(registry.list()) == 1
        with pytest.raises(ValueError): registry.register(tool)
        executor = ToolExecutor(registry)
        async def call(name='echo', arguments=None, allowed_tools=('echo','missing')):
            return await executor.execute(name, arguments or {'value':1}, allowed_tools=allowed_tools, call_id='1')
        assert (await call()).output == {'value':1}
        assert (await call(allowed_tools=())).error.code == 'TOOL_NOT_ALLOWED'
        assert (await call(name='missing')).error.code == 'TOOL_NOT_FOUND'
        assert (await call(arguments={'value':'bad'})).error.code == 'INVALID_TOOL_ARGUMENTS'
        tool.handler = lambda v: {'other':1}
        assert (await call()).error.code == 'INVALID_TOOL_OUTPUT'
        def fail(v): raise RuntimeError('secret')
        tool.handler = fail
        assert (await call()).error.code == 'TOOL_EXECUTION_ERROR'
        async def slow(v): await asyncio.sleep(1)
        tool.handler = slow
        tool.timeout = .01
        assert (await call()).error.code == 'TOOL_TIMEOUT'
    asyncio.run(check())
from ai.agents.runtime.harness import AgentHarness
from ai.agents.llm import MockLLMAdapter, TransientLLMError
from ai.agents.contracts import ExecutionLimits

def run_script(responses, **kw):
    llm = MockLLMAdapter(responses)
    harness = AgentHarness(llm, kw.pop('tools', None))
    result = asyncio.run(harness.run(definition(**kw), AgentContext(request_id='r', input_data={})))
    return result, llm

def test_harness_final_and_retry():
    result, llm = run_script([TransientLLMError('secret'), {'kind':'final','output':{'value':2}}])
    assert result.output.value == 2 and len(llm.requests) == 2
    assert 'secret' not in str(result.events)
    assert run_script([{'kind':'final','output':{}}])[0].error.code == 'INVALID_AGENT_OUTPUT'
    assert run_script([TransientLLMError('x')]*3)[0].error.code == 'LLM_TRANSIENT_ERROR'
    assert run_script([RuntimeError('x')])[0].error.code == 'LLM_EXECUTION_ERROR'
    assert run_script([{'kind':'needs_input','pending_fields':['city']}])[0].status == AgentStatus.NEEDS_INPUT
def test_loop_multiple_calls_replay_and_limits():
    registry = ToolRegistry()
    count = []
    def effect(v):
        count.append(v.value)
        return v
    registry.register(ToolDefinition(name='echo', description='Echo', input_schema=Output, output_schema=Output, handler=effect))
    call = {'id':'a','name':'echo','arguments':{'value':1}}
    responses = [{'kind':'tools','tool_calls':[call,dict(call,id='b')]},
                 TransientLLMError('x'), {'kind':'tools','tool_calls':[call]},
                 {'kind':'final','output':{'value':3}}]
    result, llm = run_script(responses, tools=registry, allowed_tools={'echo'})
    assert result.status == AgentStatus.SUCCESS and count == [1,1]
    tool_messages = [m for m in llm.requests[-1].messages if m['role']=='tool']
    assert len(tool_messages) == 3 and tool_messages[0]['output'] == {'value':1}
    assert run_script([responses[0]], tools=registry, allowed_tools={'echo'}, limits={'max_tool_calls':1})[0].error.code == 'MAX_TOOL_CALLS'
    assert run_script([responses[0]], tools=registry, allowed_tools={'echo'}, limits={'max_steps':1})[0].error.code == 'MAX_STEPS'
    assert run_script([{'kind':'tools','tool_calls':[call]}, {'kind':'tools','tool_calls':[dict(call,name='other')]}], tools=registry, allowed_tools={'echo'})[0].error.code == 'TOOL_CALL_ID_CONFLICT'

def test_timeouts_and_cancellation():
    async def check():
        cleaned = []
        class Slow:
            async def respond(self, request):
                try: await asyncio.sleep(10)
                finally: cleaned.append(True)
        ctx = AgentContext(request_id='r', input_data={})
        harness = AgentHarness(Slow())
        result = await harness.run(definition(limits={'llm_timeout':.01,'max_retries':0}),ctx)
        assert result.error.code == 'LLM_TIMEOUT' and cleaned
        result = await harness.run(definition(limits={'timeout':.01}),ctx)
        assert result.error.code == 'AGENT_TIMEOUT'
        task = asyncio.create_task(harness.run(definition(),ctx))
        await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert len(cleaned) == 3
    asyncio.run(check())
from ai.agents.skills import SkillDefinition, SkillRegistry, SkillLoader, SkillActivationError

def test_skills_loading_permissions_and_injection():
    skill = SkillLoader.from_markdown('---\n{"name":"research","description":"Research"}\n---\nOnly use mock data.')
    registry = SkillRegistry()
    registry.register(skill)
    assert registry.activate(['research'],allowed_skills={'research'})[0] == skill
    with pytest.raises(ValueError): registry.register(skill)
    for text in ('bad', '---\n{}\n---\ntext', '---\n{"name":"bad name","description":"x"}\n---\nx'):
        with pytest.raises((ValueError,ValidationError)): SkillLoader.from_markdown(text)
    with pytest.raises(SkillActivationError): registry.activate(['research'],allowed_skills=set())
    with pytest.raises(SkillActivationError): registry.activate(['missing'],allowed_skills={'missing'})
    async def check():
        llm = MockLLMAdapter([{'kind':'tools','tool_calls':[{'id':'1','name':'forbidden','arguments':{}}]},
                              {'kind':'final','output':{'value':1}}])
        harness = AgentHarness(llm,skills=registry)
        ctx = AgentContext(request_id='r', input_data={})
        result = await harness.run(definition(allowed_skills={'research'}),ctx,skills=['research'])
        assert result.status == AgentStatus.SUCCESS
        assert llm.requests[0].messages[1]['content'] == skill.instructions
        assert llm.requests[1].messages[-1]['error']['code'] == 'TOOL_NOT_ALLOWED'
        assert (await harness.run(definition(),ctx,skills=['research'])).error.code == 'SKILL_NOT_ALLOWED'
    asyncio.run(check())
@pytest.mark.parametrize('field,value', [
    ('name',''), ('name','bad name'), ('description',''), ('system_prompt',''),
    ('limits',{'max_steps':0}), ('limits',{'max_tool_calls':-1}),
    ('limits',{'max_retries':-1}), ('limits',{'timeout':0}),
    ('limits',{'llm_timeout':float('inf')}), ('limits',{'tool_timeout':-1}),
])
def test_invalid_definitions(field,value):
    data = dict(name='x',description='x',system_prompt='x',output_schema=Output)
    data[field] = value
    with pytest.raises(ValidationError): AgentDefinition(**data)

@pytest.mark.parametrize('response,code', [
    ({'kind':'final','output':{'value':'bad'}},'INVALID_AGENT_OUTPUT'),
    ({'kind':'tools','tool_calls':[]},'INVALID_LLM_RESPONSE'),
    ({'kind':'unknown'},'INVALID_LLM_RESPONSE'),
    ({'kind':'needs_input','pending_fields':[]},'INVALID_LLM_RESPONSE'),
])
def test_invalid_llm_outputs(response,code):
    assert run_script([response])[0].error.code == code

@pytest.mark.parametrize('failure_code', ['TOOL_TIMEOUT','TOOL_EXECUTION_ERROR','INVALID_TOOL_OUTPUT','INVALID_TOOL_ARGUMENTS'])
def test_loop_tool_errors_are_feedback_without_retry(failure_code):
    calls = []
    async def handler(value):
        calls.append(value)
        if failure_code == 'TOOL_TIMEOUT': await asyncio.sleep(1)
        if failure_code == 'TOOL_EXECUTION_ERROR': raise RuntimeError('credentials')
        return {} if failure_code == 'INVALID_TOOL_OUTPUT' else value
    registry = ToolRegistry()
    registry.register(ToolDefinition(name='effect',description='Effect',input_schema=Output,
        output_schema=Output,handler=handler,timeout=.01))
    call = {'id':'1','name':'effect','arguments':{'value':'bad' if failure_code == 'INVALID_TOOL_ARGUMENTS' else 1}}
    result,llm = run_script([{'kind':'tools','tool_calls':[call]},
        {'kind':'final','output':{'value':1}}],tools=registry,allowed_tools={'effect'})
    assert result.status == AgentStatus.SUCCESS
    assert llm.requests[-1].messages[-1]['error']['code'] == failure_code
    assert len(calls) == (0 if failure_code == 'INVALID_TOOL_ARGUMENTS' else 1)
    assert 'credentials' not in str(result.events)

def test_tool_cancellation_cleans_up_and_propagates():
    async def check():
        started,cleaned = asyncio.Event(),asyncio.Event()
        async def handler(data):
            started.set()
            try: await asyncio.sleep(10)
            finally: cleaned.set()
        registry = ToolRegistry()
        registry.register(ToolDefinition(name='slow',description='Slow',input_schema=Output,output_schema=Output,handler=handler))
        llm = MockLLMAdapter([{'kind':'tools','tool_calls':[{'id':'1','name':'slow','arguments':{'value':1}}]}])
        task = asyncio.create_task(AgentHarness(llm,registry).run(definition(allowed_tools={'slow'}),AgentContext(request_id='r',input_data={})))
        await asyncio.wait_for(started.wait(),1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert cleaned.is_set()
    asyncio.run(check())

def test_consecutive_tool_calls_and_output_list_schema():
    registry = ToolRegistry()
    registry.register(ToolDefinition(name='echo',description='Echo',input_schema=Output,output_schema=Output,handler=lambda v:v))
    responses = [{'kind':'tools','tool_calls':[{'id':str(i),'name':'echo','arguments':{'value':i}}]} for i in range(3)]
    responses.append({'kind':'final','output':{'value':3}})
    result,llm = run_script(responses,tools=registry,allowed_tools={'echo'})
    assert result.status == AgentStatus.SUCCESS and len(llm.requests) == 4
    async def check():
        agent = AgentDefinition(name='list',description='List',system_prompt='List',output_schema=list[Output])
        result = await AgentHarness(MockLLMAdapter([{'kind':'final','output':[{'value':2}]}])).run(agent,AgentContext(request_id='r',input_data={}))
        assert result.output == [Output(value=2)]
    asyncio.run(check())

def test_skill_file_loading(tmp_path):
    path = tmp_path / 'mock.md'
    path.write_text('---\n{"name":"mock","description":"Mock","metadata":{"version":1}}\n---\nInstructions',encoding='utf-8')
    assert SkillLoader.load(path).metadata == {'version':1}

def test_logging_contains_only_execution_labels(caplog):
    import logging
    with caplog.at_level(logging.INFO,logger='ai.agents.runtime.harness'):
        result,_ = run_script([RuntimeError('secret-api-key')])
    assert result.error.code == 'LLM_EXECUTION_ERROR'
    assert 'secret-api-key' not in caplog.text
    record = [r for r in caplog.records if r.name == 'ai.agents.runtime.harness'][-1]
    assert record.request_id == 'r'
    assert record.agent_name == 'test'
    assert record.error_code == 'LLM_EXECUTION_ERROR'
