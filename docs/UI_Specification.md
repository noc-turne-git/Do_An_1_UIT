# UI Specification

## 1. Purpose

This document is the **source of truth for the application's UI/UX structure and interaction behavior**.

The application is a travel planning product where users can:

* Explore places
* Save places
* Create and manage trips
* Chat with an AI assistant
* Build and edit itineraries
* Collect and vote on ideas
* View trip locations on an interactive map
* Collaborate with other travelers

**Important:**
Do not invent a different layout when implementing this specification.

The UI should follow the structure and interaction behavior described below.

---

# 2. Global Layout

The application uses a **two-part global layout**:

```text
┌──────────────┬──────────────────────────────────────────────┐
│              │                                              │
│   SIDEBAR    │                  CONTENT                     │
│              │                                              │
│   Chats      │                                              │
│   Trips      │                                              │
│   Explore    │                                              │
│   Saved      │                                              │
│              │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

## 2.1 Sidebar

The sidebar is fixed on the left side of the application.

Main navigation:

1. Chats
2. Trips
3. Explore
4. Saved

The sidebar remains visible while navigating between major sections.

---

# 3. Chats

## 3.1 Chats is an Overlay / Secondary Panel

When the user clicks **Chats** in the sidebar:

* Do NOT replace the entire page content.
* Open a secondary panel **on top of the current content**.
* The panel occupies approximately **35% of the main content area**.
* The current page remains visible behind the panel.

Conceptually:

```text
┌──────────────┬───────────────┬──────────────────────────────┐
│              │               │                              │
│   SIDEBAR    │ CHAT PANEL    │       CURRENT CONTENT        │
│              │               │                              │
│   Chats      │ New chat      │                              │
│   Trips      │ New trip      │                              │
│   Explore    │               │                              │
│   Saved      │ Trips         │                              │
│              │ Chats         │                              │
└──────────────┴───────────────┴──────────────────────────────┘
```

## 3.2 Chat Panel Contents

The Chats panel contains:

### Actions

* New chat
* New trip

### Trip list

Display the user's trips as a list of clickable items.

- Each trip is rendered as an interactive button/list item.
- Clicking a trip opens that trip in the main content area.

### Chat list

Display previous conversations as a list of clickable items.

- Each chat is rendered as an interactive button/list item.
- Clicking a chat opens the selected conversation in the chat view.

---

# 4. Trips Page

When the user selects **Trips** from the sidebar, display the trip management page.

## 4.1 Header

Header contains:

* Title: `Your trips`
* `+ New trip` button

Example:

```text
Your trips                                      + New trip
```

## 4.2 Trip Cards

Trips are displayed as cards.

Each card contains:

1. Cover image

2. Trip name

3. Destination

4. Duration

5. Travelers — avatars of users participating in the trip

**Travelers**

Display the avatars of users who are participating in the trip.

Avatars are displayed as a horizontal stack to save space.

If there are more travelers than can be displayed, show a `+N` indicator for the remaining users.

**Card Layout**

All trip information is displayed **on top of the cover image** as an overlay.

* **Trip name** is positioned at the **bottom-left** of the cover image.

* **Destination** is positioned below the trip name.

* **Duration** is positioned below the destination.

* **Travelers** are positioned at the **bottom-right** of the cover image.

Example:

```text
┌─────────────────────┐
│                     │
│     Trip Image      │
│                     │
│                     │
│ Da Lat Adventure    │
│ Da Lat, Vietnam     │
│ 4 days in Dec   ◯◯◯│
│                 +2  │
└─────────────────────┘
```

## 4.3 Trip Card Hover

When the user hovers over a trip card:

* Display a `...` menu button.

The menu is hidden by default.

The `...` menu button is positioned at the **top-right corner of the cover image**.

The trip name, destination, duration, and traveler avatars remain visible when hovering.

## 4.4 Trip Card Menu

Clicking `...` opens a menu containing:

* Share trip

* Change photo

* Delete trip

Visual treatment:

* Share trip → normal / black text

* Change photo → normal / black text

* Delete trip → red text

---

# 5. Trip Detail

Clicking a Trip Card (from the Trips page, or a trip from the Chats overlay trip list) opens the Trip Detail experience.

The Trip Detail experience **immediately splits the content area into two panels**, displayed side by side:

* **Left panel — Tab A — AI Conversation**
* **Right panel — Tab B — Trip Workspace**

Both panels are displayed simultaneously and are independent of each other.

```text
┌───────────────────────────────┬───────────────────────────────┐
│                               │                               │
│   LEFT PANEL (Tab A)          │   RIGHT PANEL (Tab B)         │
│   AI Conversation             │   Trip Workspace              │
│                               │                               │
└───────────────────────────────┴───────────────────────────────┘
```

**Initial state when a trip is opened:**

* Left panel → shows the trip's **Chats List** (see 6.1 and 6.5).
* Right panel → shows the Trip Workspace with the first sub-tab (`Ideas`) selected.

**Core rule:** Selecting a chat updates **only the left panel** (Tab A). The right panel (Tab B) remains unchanged.

---

# 6. Trip Detail — Tab A: AI Chat (Left Panel)

Tab A is the AI conversation panel displayed on the left side of the split-screen layout.

## 6.1 Left Panel States

The left panel has two states. Only one is visible at a time.

**Shared by both states (always visible at the top of the left panel):**

* **Header** (6.2): Back button, trip name + destination, Where / When / Who / Budget.
The **AI Alert** (6.3) is an AI-generated summary / warning about the trip's **main chat**. It appears only in State A1.

**State A1 — Chats List**

* Shown when the trip is first opened.
* Contains: shared Header + AI Alert (about the main chat) + **TripChatsList** (see 6.5).

**State A2 — Conversation**

* Shown after the user clicks a chat in the Chats List.
* Contains: shared Header + the selected AI conversation + Chat Input (see 6.4). The AI Alert is hidden in this state.
* The `Back` button in the header returns the left panel to State A1.

```text
State A1                          State A2
┌──────────────────────┐          ┌──────────────────────┐
│ Header (shared)      │          │ Header (shared)      │
├──────────────────────┤          ├──────────────────────┤
│ AI Alert (main chat) │          │                      │
├──────────────────────┤          ├──────────────────────┤
│ TripChatsList        │          │ Conversation         │
│  • Chat 1  [Main]    │          │                      │
│  • Chat 2            │          ├──────────────────────┤
│  • Chat 3            │          │ Chat Input      Send │
└──────────────────────┘          └──────────────────────┘
```

```text
        click a chat
  A1 ─────────────────▶ A2
  Chats List            Conversation
     ◀─────────────────
          click Back
```

Switching between A1 and A2 (and between different chats) must **never** affect the right panel.

The Header is shared by both states. The AI Alert is displayed only in State A1 and is hidden in State A2; switching states only changes the left panel's content and never affects the right panel.

## 6.2 Header

The header is displayed at the top of the left panel and is **shared by both states** (A1 and A2) of the Trip Detail.

Display:

* **Back button** — displayed in both states:
  * In State A2 (Conversation) → returns to the Chats List (State A1).
  * In State A1 (Chats List) → returns to the Trips page (`Your trips`).

* **Trip name** — with the **destination displayed below it**.

* **Where**, **When**, **Who**, **Budget** controls.

The `Where`, `When`, `Who`, and `Budget` controls are displayed **horizontally in a single row**, below the trip name / destination.

These controls allow the user to modify high-level trip information.

```text
┌────────────────────────────────────────────┐
│ ←  Da Lat Adventure                        │
│    Da Lat, Vietnam                         │
│                                            │
│  Where     When     Who     Budget         │
└────────────────────────────────────────────┘
```

The header does **not** contain the trip utility actions (Invite, Share / Export, More, Add Note). Those belong to the top-right area of the right panel (see Section 12).

## 6.3 AI Summary / Alert

Below the header, in **State A1 only**, display an AI-generated summary or warning based on the **main chat**. Hide this alert in State A2.

Example:

> Your itinerary has lots of stops but no transport booked between Da Lat and TP.HCM on Day 4. Want help lining up a ride back and timing it with your last activities?

This section should visually communicate useful AI-generated trip insights.

## 6.4 Conversation and Chat Input

In State A2, below the header, the panel contains:

* **Conversation area** — scrollable list of user messages and AI responses.

* **Chat input** — displayed at the bottom of the panel.

The chat input includes:

* Text input

* Send button

The input should remain easily accessible while scrolling through the conversation.

## 6.5 Chats List

In State A1, below the AI Alert, display the **TripChatsList**: a list of previous conversations related to the trip.

Each chat item contains:

* Chat name

* Last updated date

* Hidden `...` menu button

If the chat is the **main chat**, display a `Main` label next to the chat name.

When the user selects a chat, the left panel switches to State A2 and displays the selected conversation. **The right panel (Tab B) remains unchanged.**

The `...` menu button is hidden by default and only appears when the user hovers over the chat item.

Clicking `...` opens a menu containing:

* Rename chat

* Set as main chat

* Delete chat

The **Set as main chat** option allows the user to designate the selected conversation as the primary chat for the trip.

---

# 7. Trip Detail — Tab B: Trip Workspace (Right Panel)

Tab B is the detailed trip management workspace, displayed in the right panel.

It is a more comprehensive editing environment than the conversational Tab A.

Tab B is independent of the left panel. It does not change when the user opens, switches, or closes a chat in Tab A.

### 7.1 Workspace Sub-tabs

The Trip Workspace contains five sub-tabs displayed in a single horizontal row:

```text
Ideas    Itinerary    Trip preferences    Calendar    Map
```

Each sub-tab represents a different workspace view.

The workspace uses a **shared content area** below the sub-tab navigation.

```text
┌────────────────────────────────────────────────────────────────┐
│ Ideas | Itinerary | Trip preferences | Calendar | Map          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│                       Shared Content                            │
│                                                                │
│             Content changes based on selected tab              │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

Only one sub-tab can be selected at a time.

When the user selects a sub-tab, the shared content area is replaced with the corresponding content of that sub-tab.

For example:

* **Ideas** → displays the Ideas interface.
* **Itinerary** → displays the Itinerary interface.
* **Trip preferences** → displays the Trip Preferences interface.
* **Calendar** → displays the Calendar interface.
* **Map** → displays the Trip Map interface.

The sub-tab navigation remains visible while switching between views.

The selected tab should have a visually distinct active state.

### 7.2 Shared Content Area

The shared content area is a single reusable container located directly below the sub-tab navigation.

Its content changes according to the selected sub-tab.

```text
┌────────────────────────────────────────────────────────────────┐
│ Ideas    Itinerary    Trip preferences    Calendar    Map      │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│                   SELECTED TAB CONTENT                         │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

The shared content area must not create separate panels for each sub-tab. Only the content of the currently selected sub-tab is rendered.

---

# 8. Ideas

Ideas are places, restaurants, activities, or other suggestions that have been collected but are not necessarily confirmed for the itinerary.

When the **Ideas** sub-tab is selected, the content area displays:

### 8.1 Header

```text
Ideas
2 items
```

The top-right toolbar contains:

```text
+ Add    Type    ...
```

* **+ Add** — add a new idea.
* **Type** — filter ideas by type.
* **...** — open additional actions.

### 8.2 Idea Cards

Ideas are displayed as cards in a two-column grid.

Each card contains:

* Cover image
* Place/activity name
* Type/category

Example:

```text
┌─────────────────────┐  ┌─────────────────────┐
│                     │  │                     │
│       Image         │  │       Image         │
│                     │  │                     │
├─────────────────────┤  ├─────────────────────┤
│ Lam Vien Square     │  │ Dalat Flower        │
│ Attraction          │  │ Plateau             │
│                     │  │ Attraction          │
└─────────────────────┘  └─────────────────────┘
```

The example place names are illustrative only.

### 8.3 Card Actions

When the user hovers over an idea card, a heart button for saving and a `...` button for additional actions appear.

The menu may contain actions such as:

* Add to itinerary
* Edit
* Delete
* View details

---

# 9. Itinerary

When the **Itinerary** sub-tab is selected, the content area displays the confirmed trip schedule organized by day.

### 9.1 Header

```text
Itinerary
4 days                                      Distances   ...
```

The header contains:

* **Itinerary** — page title.
* **4 days** — total number of itinerary days.
* **Distances** — toggle for displaying distances between locations.
* **...** — additional itinerary actions.

### 9.2 Day Sections

Each day is displayed as a vertical timeline/list.

Example:

```text
Day 1

[Image]  Xuan Huong Lake
         09:00 – 10:30
         8.95 km

[Image]  Yersin Park
         11:00 – 12:00
         2.4 km

                         + Add place
```

Each itinerary item may contain:

* Place/activity image
* Place/activity name
* Start time
* End time
* Distance to the next place

### 9.3 Item Actions

When hovering over an itinerary item, action controls appear:

```text
...    Comment
```

The `...` menu provides additional item actions.

### 9.4 Comments

Selecting **Comment** opens a comment area below the itinerary item.

```text
┌──────────────────────────────────────────┐
│ [Avatar]  Add a comment             Send │
└──────────────────────────────────────────┘
```

Users can enter a comment and select **Send** to add it to the itinerary item.

### 9.5 Add Place

At the bottom of each day, an add button is displayed:

```text
+ Add place
```

This allows users to add a new place/activity to that day.

---

# 10. Trip Preferences

When the **Trip preferences** sub-tab is selected, the content area displays the trip's global preferences.

### 10.1 Header

```text
Trip preferences
```

### 10.2 Suggested Preferences

The system may suggest preferences based on the trip context.

Suggestions are displayed as pale-yellow boxes:

```text
┌──────────────────────────────────────────────┐
│ Prefer short travel distances     Accept  × │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│ Avoid rainy days                  Accept  × │
└──────────────────────────────────────────────┘
```

Each suggestion contains:

* Suggested preference text
* **Accept** button
* `×` button to dismiss the suggestion

### 10.3 Add Preference

Below the suggestions, users can manually add a preference.

```text
┌──────────────────────────────────────────────┐
│ We prefer hotels with free breakfast       + │
└──────────────────────────────────────────────┘
```

The `+` button adds the entered preference to the trip preferences.

---

# 11. Calendar

When the **Calendar** sub-tab is selected, the content area displays the itinerary in a calendar-based view.

### 11.1 Header

```text
Calendar
4 days
```

### 11.2 Calendar Navigation

Days are displayed as columns:

```text
        Day 1     Day 2     Day 3     Day 4

        ←                              →
```

Navigation arrows allow users to move through the calendar.

### 11.3 All-day Events

An all-day row is displayed above the hourly timeline.

Example:

```text
All-day

        ┌────────────────────────────────────┐
Day 1   │ D House Dalat                      │
        └────────────────────────────────────┘
```

### 11.4 Time Grid

The calendar contains a vertical time axis:

```text
1 PM
2 PM
3 PM
4 PM
5 PM
6 PM
7 PM
8 PM
```

The four days are displayed horizontally.

### 11.5 Event Blocks

Activities are represented as blocks positioned according to their day and time.

Example:

```text
          Day 1          Day 2          Day 3          Day 4

1 PM      ┌─────────┐
          │ Xuan    │
          │ Huong   │
          │ Lake    │
          └─────────┘

3 PM                     ┌─────────┐
                         │ Yersin  │
                         │ Park    │
                         └─────────┘

6 PM      ┌────────────┐
          │ Da Lat     │
          │ Night      │
          │ Market     │
          └────────────┘
```

The position and size of each event block correspond to its scheduled day and duration.

---

# 12. Trip Workspace Header Actions

The top-right area of the Trip Workspace (the right panel) contains utility actions. They are displayed above the workspace sub-tabs and remain visible at all times, regardless of the selected sub-tab and regardless of the state of the left panel.

```text
┌────────────────────────────────────────────────────────────────┐
│                     ◯◯◯ Invite   Share   Add note   ...        │
├────────────────────────────────────────────────────────────────┤
│ Ideas | Itinerary | Trip preferences | Calendar | Map          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│                       Shared Content                            │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

Required actions:

### Invite

Allows users to invite friends / travel companions.

Display participant avatars when appropriate.

### Share / Export

Provides the option to: Copy a shareable link

### More (`...`)

Advanced actions may include:

* Export trip data
* Duplicate trip
* Archive trip
* Delete trip

### Add Note

Allows the user to add a note to the trip/workspace.

---

# 13. Map Sub-tab

The **Map** is the fifth sub-tab of the Trip Workspace (see 7.1).

When the **Map** sub-tab is selected:

* Only the shared content area (below the sub-tab navigation) changes into the interactive map.
* The sub-tab navigation and the utility actions (Section 12) remain visible.
* The left panel (AI chat / Chats List) remains unchanged.
* Do NOT replace the entire application.

There is no separate "Map toggle" or map page. Map is a view mode of the right panel, reached only through the sub-tab.

```text
┌──────────────────────────────┬──────────────────────────────────┐
│ ← Da Lat Adventure           │     ◯◯◯ Invite  Share  Note  ... │
│   Da Lat, Vietnam            ├──────────────────────────────────┤
│ Where When Who Budget        │ Ideas Itinerary Prefs Calendar Map│
│                              ├──────────────────────────────────┤
│         AI CHAT              │                                  │
│                              │              MAP                 │
│                              │                                  │
│                              │    ◉ Langbiang                   │
│                              │    ◉ Puppy Farm                  │
│                              │    ◉ Datanla                     │
│                              │                          + -     │
└──────────────────────────────┴──────────────────────────────────┘
```

---

# 14. Map Visual Style

The map should use a light, clean map style.

Google Maps may be used as the map provider.

The map should emphasize:

* Trip locations
* Routes
* Geographic relationships  
* Distances between places

The map should not visually overpower the trip workspace.

---

# 15. Map Markers

Each itinerary location can be represented by a circular marker.

A marker contains an icon representing the type of location.

Examples:

* Camera → attraction
* Mountain → outdoor/nature
* Coffee cup → cafe
* Restaurant icon → restaurant
* Other relevant icons → corresponding category

Example:

```text
   ◉ Langbiang
   ◉ Puppy Farm
   ◉ Datanla Waterfall
   ◉ Tuyen Lam Lake
   ◉ Cau Dat Farm
```

The marker may display the location name beside it.

---

# 16. Marker Clustering

When multiple locations are geographically close:

* Group them into a cluster.
* Avoid displaying too many overlapping markers.
* Expanding/zooming the map should reveal individual markers.

Example:

```text
        ┌─────┐
        │  7  │
        └─────┘

       clustered
       locations
```

---

# 17. Map Controls

Map controls are positioned in the bottom-right corner.

Required controls:

1. Current location / recenter
2. Map layers
3. Zoom in
4. Zoom out

The map may also display standard map attribution and scale information required by the map provider.

---

# 18. Trip Detail Split View — Behavior

This section defines how the two panels behave together after a trip is opened.

## 18.1 Layout

```text
┌───────────────────────────────┬────────────────────────────────┐
│ LEFT PANEL (Tab A)            │ RIGHT PANEL (Tab B)            │
│                               │                                │
│ Header (shared A1 + A2)       │ Utility actions (top-right)    │
│                               │ Sub-tabs                       │
│ ─ State A1: AI Alert (main chat)|                              |
   TripChatsList                │ Shared content                 │
│   or                          │ (Ideas / Itinerary /           │
│ ─ State A2: Conversation      │  Trip preferences / Calendar / │
│   + Chat Input                │  Map)                          │
└───────────────────────────────┴────────────────────────────────┘
```

## 18.2 Interaction Flow

1. The user selects **Trips** in the sidebar → the Trips page (list of trip cards) is displayed.
2. The user clicks a trip card → the content area splits into two panels:
   * Left panel → State A1: shared Header + AI Alert (about the main chat) + TripChatsList.
   * Right panel → Trip Workspace (default sub-tab: `Ideas`).
3. The user clicks a chat in the Chats List (left panel) → the left panel changes to State A2 and shows the AI conversation with the user. The Header stays in place, the AI Alert is hidden, and the conversation is shown below the header.
4. **The right panel stays exactly as it was.**
5. The user clicks **Back** in the left header while in State A2 → the left panel returns to State A1 (Chats List). The right panel still stays unchanged.
6. The user can select another chat at any time → only the left panel changes.
7. The user clicks **Back** in the left header while in State A1 → the user leaves Trip Detail and returns to the Trips page.

## 18.3 What "unchanged" means for the right panel

When the left panel changes (chat selected, chat switched, Back pressed), the right panel must preserve:

* The currently selected sub-tab (Ideas / Itinerary / Trip preferences / Calendar / Map).
* Scroll position inside the shared content area.
* Map viewport (center, zoom, clusters) when the Map sub-tab is active.
* Any in-progress input (e.g. an open comment box, a preference being typed).
* The utility actions area.

The right panel must not be re-mounted, reset, or re-fetched as a side effect of any left-panel change.

## 18.4 Header placement summary

| Element | Location |
|---|---|
| Back button | Left panel header (shared by A1 and A2) |
| Trip name + destination (below) | Left panel header (shared by A1 and A2) |
| Where / When / Who / Budget | Left panel header (single row, shared by A1 and A2) |
| AI Alert (about main chat) | Left panel, directly below the header in A1 only |
| Invite (+ avatars) | Top-right of right panel |
| Share / Export | Top-right of right panel |
| Add note | Top-right of right panel |
| More (`...`) | Top-right of right panel |

---

# 19. State Model

The UI should be treated as a set of explicit states rather than separate unrelated pages.

Important states include:

```text
GLOBAL
│
├── Sidebar
│
├── Chats Overlay
│
├── Trips
│   └── Trip Cards
│
└── Trip Detail (split view: two independent panels)
    │
    ├── Left panel (Tab A)
    │   ├── Shared: Header + AI Alert (main chat)
    │   └── Exactly one of:
    │       ├── A1: TripChatsList
    │       └── A2: Conversation (selected chat) + Chat Input
    │
    └── Right panel (Tab B) ── Trip Workspace, exactly one sub-tab:
        ├── Ideas
        ├── Itinerary
        ├── Trip Preferences
        ├── Calendar
        └── Map
```

The left-panel state and the right-panel sub-tab state are **independent**. Changing one never changes the other.

---

# 20. Critical Interaction Rules

These rules are especially important.

## Rule 1 — Chats is an overlay

Clicking `Chats` does not navigate away from the current page.

It opens a panel over the existing content.

## Rule 2 — Trip cards open a split view

Clicking a Trip Card opens Trip Detail, which is immediately displayed as two panels: left (AI Chat / Chats List) and right (Trip Workspace).

## Rule 3 — Left panel is conversational

The left panel prioritizes AI conversation and trip planning through natural language. It has a shared Header and an AI Alert shown in State A1, plus two states below them: Chats List (A1) and Conversation (A2).

## Rule 4 — Right panel is operational

The right panel prioritizes detailed trip management: Ideas, Itinerary, Trip preferences, Calendar, Map.

## Rule 5 — Selecting a chat changes only the left panel

Selecting, switching, or leaving a chat updates only the left panel. The right panel remains unchanged (see 18.3).

## Rule 6 — Back is context-aware and never touches the right panel

The Back button is part of the shared left header and is always visible in Trip Detail.

* In State A2 (Conversation) → returns to the Chats List (A1).
* In State A1 (Chats List) → returns to the Trips page.

In both cases the right panel is not modified.

## Rule 7 — Header responsibilities are split

* Left panel header (shared by A1 and A2): Back, trip name, destination, Where / When / Who / Budget.
* Right panel top-right: Invite, Share / Export, More (`...`), Add note.

## Rule 8 — Map is a sub-tab

Map is not a separate page or toggle. It is the fifth sub-tab of the Trip Workspace and replaces only the shared content area of the right panel.

## Rule 9 — No extra header buttons

The `Go to trip`, `Close`, and `Expand` buttons must not exist in the Trip Detail header. The split view is the only Trip Detail layout.

## Rule 10 — Do not invent navigation

Do not introduce additional major navigation levels that are not described in this document.

---

# 21. Responsive Behavior

The UI should adapt to different screen sizes.

However, responsive behavior must preserve the hierarchy:

```text
Sidebar
    ↓
Current Content
    ↓
Contextual overlays / panels
    ↓
Trip Detail split view (left panel + right panel)
```

On smaller screens, panels may become full-screen or stack vertically when necessary.

The interaction model should remain understandable, and the independence of the left and right panels must be preserved.

---

# 22. Visual Direction

The visual style should be:

* Modern
* Clean
* Minimal
* Image-heavy
* Spacious
* Rounded cards
* Light background
* Strong typography
* Subtle borders
* Minimal shadows

Avoid:

* Excessive decoration
* Heavy gradients
* Excessive shadows
* Dense layouts
* Unnecessary UI elements
* Overly colorful interfaces

The interface should feel like a modern travel planning product.

---

# 23. Implementation Guidance

When implementing this specification:

1. Read this file before creating or modifying UI components.
2. Preserve the layout hierarchy described above.
3. Treat the interaction rules as functional requirements, not visual suggestions.
4. Prefer reusable components for repeated UI patterns.
5. Keep UI state explicit.
6. Keep the left-panel state (`chatsList` | `conversation(chatId)`) and the right-panel state (`activeSubTab`) as **separate, independent state**.
7. Do not re-mount or reset the right panel when the left-panel state changes. Keep `ChatHeader` shared by A1 and A2; render `AIAlert` only in A1.
8. Keep the AI chat independent from the Trip Workspace so both coexist in split view.
9. Keep the map as a replaceable view inside the Trip Workspace shared content area (a sub-tab, not a page).
10. Do not add features or navigation patterns that contradict this specification.

---

# 24. Component Concept

The implementation can conceptually follow this hierarchy:

```text
App
│
├── Sidebar
│   ├── Chats
│   ├── Trips
│   ├── Explore
│   └── Saved
│
├── ChatsOverlay
│   ├── NewChat
│   ├── NewTrip
│   ├── TripList
│   └── ChatList
│
└── MainContent
    │
    ├── TripsPage
    │   └── TripCard
    │
    └── TripDetail (TripSplitView)
        │
        ├── LeftPanel (Tab A)
        │   ├── ChatHeader                 ← shared by A1 and A2
        │   │   ├── BackButton
        │   │   ├── TripTitle (name + destination)
        │   │   └── TripControls (Where / When / Who / Budget)
        │   ├── AIAlert (main chat)        ← shared by A1
        │   └── Exactly one of:
        │       ├── TripChatsList          ← State A1
        │       └── AIChatView             ← State A2
        │           ├── Conversation
        │           └── ChatInput
        │
        └── RightPanel (Tab B) = TripWorkspace
            ├── WorkspaceHeaderActions
            │   ├── Invite
            │   ├── ShareExport
            │   ├── AddNote
            │   └── More
            ├── WorkspaceTabs
            │   ├── Ideas
            │   ├── Itinerary
            │   ├── TripPreferences
            │   ├── Calendar
            │   └── Map
            └── WorkspaceContent (shared content area)
                └── TripMap (rendered when Map is selected)
```

---

# 25. Priority

When implementation decisions conflict, prioritize in this order:

1. **Interaction behavior**
2. **Layout hierarchy**
3. **Trip / Chat relationship**
4. **Information architecture**
5. **Visual styling**
6. **Decorative details**

Do not sacrifice the interaction model merely to achieve a visually attractive layout.
