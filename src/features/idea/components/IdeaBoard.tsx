import { useMemo, useState } from 'react'
import { IdeaCard } from './IdeaCard'
import { INITIAL_IDEAS } from './ideaData'
import { DetailsModal, IdeaForm, ItineraryModal, Modal } from './IdeaModals'
import type { Idea, IdeaAction, IdeaBoardProps, IdeaDialog } from './ideaTypes'

export function IdeaBoard({ onAddToItinerary, initialIdeas = INITIAL_IDEAS }: IdeaBoardProps) {
  const [ideas, setIdeas] = useState<Idea[]>(initialIdeas)
  const [filter, setFilter] = useState('All types')
  const [savedIdeas, setSavedIdeas] = useState<string[]>([])
  const [openMenu, setOpenMenu] = useState<string | null>(null)
  const [dialog, setDialog] = useState<IdeaDialog>(null)
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [type, setType] = useState('Attraction')
  const [price, setPrice] = useState('')
  const [currency, setCurrency] = useState('VND')
  const [image, setImage] = useState('')
  const [day, setDay] = useState('Day 1')
  const [allDay, setAllDay] = useState(false)

  const visibleIdeas = useMemo(
    () => ideas.filter((idea) => filter === 'All types' || idea.type === filter),
    [ideas, filter],
  )
  const ideaTypes = useMemo(() => [...new Set(ideas.map((idea) => idea.type))], [ideas])
  const selectedIdea = ideas.find((idea) => idea.name === selectedName)

  const closeDialog = () => setDialog(null)

  const openAddDialog = () => {
    setSelectedName(null)
    setName('')
    setType('Attraction')
    setPrice('')
    setCurrency('VND')
    setImage('')
    setDialog('add')
  }

  const openEditDialog = (idea: Idea) => {
    setSelectedName(idea.name)
    setName(idea.name)
    setType(idea.type)
    setPrice(idea.price === undefined ? '' : String(idea.price))
    setCurrency(idea.currency ?? 'VND')
    setImage(idea.image)
    setDialog('edit')
  }

  const openDetailsDialog = (idea: Idea) => {
    setSelectedName(idea.name)
    setDialog('details')
  }

  const openItineraryDialog = (idea: Idea) => {
    setSelectedName(idea.name)
    setDay('Day 1')
    setAllDay(false)
    setDialog('itinerary')
  }

  const saveIdea = () => {
    const cleanName = name.trim()
    if (!cleanName) return

    const cleanType = type.trim() || 'Other'
    const details = { name: cleanName, type: cleanType, image: image || 'photo-1500530855697-b586d89ba3ee', price: price === '' ? undefined : Number(price), currency }
    if (dialog === 'edit' && selectedName) {
      setIdeas((currentIdeas) => currentIdeas.map((idea) =>
        idea.name === selectedName ? { ...idea, ...details } : idea,
      ))
      if (selectedName !== cleanName) setSelectedName(cleanName)
    } else {
      setIdeas((currentIdeas) => [
        ...currentIdeas,
        details,
      ])
    }

    closeDialog()
  }

  const toggleSaved = (ideaName: string) => {
    setSavedIdeas((current) => current.includes(ideaName)
      ? current.filter((savedName) => savedName !== ideaName)
      : [...current, ideaName],
    )
  }

  const handleAction = (action: IdeaAction, idea: Idea) => {
    setOpenMenu(null)

    switch (action) {
      case 'itinerary':
        openItineraryDialog(idea)
        break
      case 'edit':
        openEditDialog(idea)
        break
      case 'details':
        openDetailsDialog(idea)
        break
      case 'delete':
        setIdeas((currentIdeas) => currentIdeas.filter((item) => item.name !== idea.name))
        setSavedIdeas((currentSaved) => currentSaved.filter((item) => item !== idea.name))
        break
    }
  }

  const confirmItinerary = () => {
    if (!selectedIdea) return
    onAddToItinerary(selectedIdea.name)
    closeDialog()
  }

  return (
    <section>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Ideas</h2>
          <p className="mt-1 text-sm text-neutral-500">
            {visibleIdeas.length} {visibleIdeas.length === 1 ? 'item' : 'items'}
          </p>
        </div>

        <div className="flex gap-2">
          <button onClick={openAddDialog} className="rounded-full bg-neutral-950 px-4 py-2 text-sm font-medium text-white">＋ Add</button>
          <select
            aria-label="Filter ideas by type"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            className="rounded-full border border-neutral-200 bg-white px-4 py-2 text-sm"
          >
            <option>All types</option>
            {ideaTypes.map((ideaType) => <option key={ideaType}>{ideaType}</option>)}
          </select>
        </div>
      </header>

      {visibleIdeas.length === 0 && <p className="mb-5 rounded-xl border border-dashed border-neutral-200 p-6 text-center text-sm text-neutral-500">No ideas yet. Add a place or activity for this trip.</p>}

      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {visibleIdeas.map((idea, index) => (
          <IdeaCard
            key={idea.name}
            idea={idea}
            index={index}
            liked={savedIdeas.includes(idea.name)}
            menuOpen={openMenu === idea.name}
            onViewDetails={() => openDetailsDialog(idea)}
            onToggleLike={() => toggleSaved(idea.name)}
            onToggleMenu={() => setOpenMenu((current) => current === idea.name ? null : idea.name)}
            onAction={(action) => handleAction(action, idea)}
          />
        ))}
      </div>

      {selectedIdea && dialog === 'details' && (
        <Modal onClose={closeDialog}>
          <DetailsModal
            idea={selectedIdea}
            onClose={closeDialog}
            onAddToItinerary={() => openItineraryDialog(selectedIdea)}
          />
        </Modal>
      )}

      {selectedIdea && dialog === 'itinerary' && (
        <Modal onClose={closeDialog}>
          <ItineraryModal
            idea={selectedIdea}
            day={day}
            allDay={allDay}
            onDayChange={setDay}
            onAllDayChange={setAllDay}
            onConfirm={confirmItinerary}
            onClose={closeDialog}
          />
        </Modal>
      )}

      {(dialog === 'add' || (dialog === 'edit' && selectedIdea)) && (
        <Modal onClose={closeDialog}>
          <IdeaForm
            mode={dialog === 'edit' ? 'edit' : 'add'}
            name={name}
            type={type}
            price={price}
            currency={currency}
            image={image}
            onPriceChange={setPrice}
            onCurrencyChange={setCurrency}
            onImageChange={setImage}
            onNameChange={setName}
            onTypeChange={setType}
            onSave={saveIdea}
            onClose={closeDialog}
          />
        </Modal>
      )}
    </section>
  )
}
