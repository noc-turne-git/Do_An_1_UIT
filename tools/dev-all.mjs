import { existsSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';

const root = process.cwd();
const isWindows = process.platform === 'win32';
const venvPython = resolve(
  root,
  isWindows ? '.venv/Scripts/python.exe' : '.venv/bin/python',
);
const python = existsSync(venvPython) ? venvPython : 'python';
const npm = isWindows ? 'npm.cmd' : 'npm';

const processes = [
  spawn(npm, ['--prefix', 'frontend', 'run', 'dev'], {
    cwd: root,
    stdio: 'inherit',
    // Windows requires a shell to launch .cmd files such as npm.cmd.
    shell: isWindows,
  }),
  spawn(
    python,
    [
      '-m',
      'uvicorn',
      'app.main:app',
      '--app-dir',
      'backend',
      '--reload',
      '--host',
      '127.0.0.1',
      '--port',
      '8001',
    ],
    { cwd: root, stdio: 'inherit' },
  ),
];

let stopping = false;
function stop(exitCode = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of processes) child.kill('SIGTERM');
  process.exit(exitCode);
}

for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => stop());

for (const child of processes) {
  child.on('error', (error) => {
    console.error(`Could not start ${child.spawnfile}: ${error.message}`);
    stop(1);
  });
  child.on('exit', (code) => {
    if (!stopping) stop(code ?? 1);
  });
}
