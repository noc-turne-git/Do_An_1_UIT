# Frontend Architecture

## 1. Overview

This document defines the technical architecture and code organization of the **frontend** of the travel planning application.

It describes:

* Project structure
* Responsibilities of each directory
* Dependency and import rules
* Component and feature organization
* Data flow and state management
* API communication
* Rules for adding new code

Related documents:

```text
docs/UI_Specification.md        → how the interface looks and behaves
docs/Product_Specification.md   → what the product does
docs/Data_Model.md              → how application data is structured
docs/State_Model.md             → how UI/application states transition
docs/Development_Rules.md       → rules for implementing and modifying code
```

The backend is out of scope for this document. The frontend only depends on the backend through the API contract (see section 12).

---

# 2. Technology Stack

* React
* TypeScript
* Vite
* React Router
* Tailwind CSS
* Server state: TanStack Query
* Client state: Zustand (only for state shared across components; prefer local state first)
* HTTP client: fetch (wrapped in `services/api`)
* Testing: Vitest + React Testing Library

> Items marked with a specific library are the project defaults. Changing one requires updating this document.

---

# 3. Directory Structure

```text
frontend/
├── src/
│   ├── app/
│   ├── pages/
│   ├── features/
│   ├── components/
│   ├── hooks/
│   ├── services/
│   ├── types/
│   ├── utils/
│   └── assets/
│
├── public/
└── ...
```

---

# 4. `app/`

Application-level configuration.

```text
app/
├── App.tsx
├── routes.tsx
└── providers/
```

Responsibilities:

* Application entry
* Routing
* Global providers (Query client, router, theme, auth)
* Global configuration

Do not put feature-specific logic here.

---

# 5. `pages/`

Page-level components, one per major route.

```text
pages/
├── HomePage.tsx
├── ExplorePage.tsx
├── TripsPage.tsx
└── TripPage.tsx
```

Pages compose feature components and handle route params and layout.
Pages must not contain business logic or API calls.

---

# 6. `features/`

Domain-specific functionality.

```text
features/
├── trip/
├── chat/
├── place/
├── itinerary/
├── idea/
├── map/
└── user/
```

Each feature owns its components, hooks, services, types, and logic:

```text
features/trip/
├── components/
├── hooks/
├── services/
├── types.ts
├── __tests__/
└── index.ts        ← public API of the feature
```

### Public API rule

Each feature exposes only what other code may use through `index.ts`.
Anything not exported from `index.ts` is private to the feature.

---

# 7. `components/`

Reusable UI components that are **not** tied to any domain.

```text
components/
├── Button/
├── Modal/
├── Card/
├── Dropdown/
├── Avatar/
└── Tabs/
```

A shared component must not know about trips, places, chat, or any other domain concept.

* `components/Button` → correct
* `features/trip/components/TripActionButton` → correct for a trip-specific button

---

# 8. `hooks/`

Generic reusable hooks that are not tied to a domain.

```text
hooks/
├── useDebounce.ts
├── useModal.ts
└── useMediaQuery.ts
```

Domain hooks live in their feature, e.g. `features/trip/hooks/useTrip.ts`.

---

# 9. `services/`

Global infrastructure only. No domain logic.

```text
services/
├── api/        ← HTTP client, interceptors, error normalization
├── auth/
├── maps/
└── storage/
```

Feature-specific API functions (e.g. `addPlaceToTrip`) live in `features/<feature>/services/` and use the global API client.

```text
services/api          → how to make a request
features/trip/services → which requests the trip domain makes
```

UI components must not call `fetch` or the API client directly.

---

# 10. `types/`

Shared TypeScript types used by **two or more features**.

```text
types/
├── user.ts
├── trip.ts
├── place.ts
└── itinerary.ts
```

Types used by only one feature stay in that feature's `types.ts`.

---

# 11. `utils/`

Small, pure, framework-independent helper functions.

```text
utils/
├── date.ts
├── format.ts
├── validation.ts
└── constants.ts
```

Utilities must not contain UI logic or import from `features/`.

---

# 12. API Communication

* All requests go through `services/api`.
* Feature services define domain functions such as `tripService.addPlace()`.
* Hooks call feature services; components call hooks.
* Request/response types are defined in `types/` or in the feature's `types.ts`, and mirror the backend API contract.
* The API base URL comes from environment config (`VITE_API_BASE_URL`), never hard-coded.

Errors are normalized in `services/api` into a single shape so that hooks and components handle them consistently.

---

# 13. Dependency and Import Rules

Allowed dependency direction:

```text
pages → features → components / hooks / services / types / utils
```

Rules:

1. `pages/` may import from `features/`, `components/`, `hooks/`, `types/`, `utils/`.
2. `features/` may import from `components/`, `hooks/`, `services/`, `types/`, `utils/`.
3. `features/` must **not** import from `pages/`.
4. `components/`, `hooks/`, `services/`, `types/`, `utils/` must **not** import from `features/` or `pages/`.
5. A feature may import another feature **only** through that feature's `index.ts`. Never import deep paths such as `features/trip/hooks/internal/...`.
6. Avoid circular dependencies between features. If two features need each other, extract the shared part or communicate through a service/store.

---

# 14. Data Flow

```text
User interaction
      ↓
React component
      ↓
Feature hook (TanStack Query / Zustand)
      ↓
Feature service
      ↓
services/api
      ↓
Backend API
```

Example:

```text
User clicks "Add to Trip"
        ↓
PlaceCard (features/place)
        ↓
useAddPlaceToTrip()
        ↓
tripService.addPlace()
        ↓
POST /trips/{tripId}/places
```

---

# 15. State Management

### Local UI state

Modal open/closed, dropdown, active tab, hover, form input.
Use `useState` / `useReducer` inside the component.

### Feature (client) state

State shared across several components of a feature or across features that is **not** from the server, such as the currently selected place, map viewport, or chat draft.
Use Zustand, with one store per feature located in `features/<feature>/store/`.

### Server state

Everything fetched from the backend: trips, places, itinerary, messages.
Use TanStack Query:

* Query keys are defined per feature (e.g. `tripKeys.detail(tripId)`).
* Mutations invalidate or update the related queries.
* Do not copy server data into Zustand.

---

# 16. Cross-Feature Communication

Features must not manipulate each other's internals.

Example: Chat must not modify Trip state directly.

```text
Chat
  ↓
Trip public API (features/trip/index.ts) or trip service
  ↓
Trip
```

After a chat action changes a trip, refresh the trip by invalidating the relevant query, not by writing into the trip store from the chat feature.

---

# 17. Routing

Routes are defined centrally in `src/app/routes.tsx`.

```text
/
├── /explore
├── /trips
├── /trips/:tripId
└── /saved
```

Do not define routes inside feature components.

---

# 18. Shared vs Feature Components

**Shared** (generic): `Button`, `Modal`, `Dropdown`, `Tabs`, `Card`, `Avatar`

**Feature** (domain-aware): `TripCard`, `ItineraryItem`, `IdeaCard`, `ChatMessage`, `TripHeader`

Rule of thumb: if the component would have to know what a trip, place, or message is, it belongs in a feature.

---

# 19. Naming Conventions

* React components and their files: `PascalCase` (`TripCard.tsx`)
* Hooks: `camelCase` starting with `use` (`useTrip.ts`)
* Functions and variables: `camelCase`
* Types and interfaces: `PascalCase`
* Constants: `UPPER_SNAKE_CASE`
* Feature folders: lowercase singular (`trip`, `chat`)

Avoid generic names such as `Component.tsx`, `Data.ts`, `Helper.ts`, `Manager.ts`.

---

# 20. Loading, Empty, Success, and Error States

Every data-driven feature defines all four states:

```text
Loading
Empty
Success
Error
```

Example, trip list:

```text
Trip list
├── Loading
├── Empty
├── Loaded
└── Error
```

Network errors are handled at the hook/service layer and surfaced to components in a consistent shape. Components should not each implement their own error parsing.

---

# 21. Testing

Tests live next to the code they cover:

```text
features/trip/
├── components/
├── hooks/
├── services/
└── __tests__/
```

Prioritize tests for:

* Business logic in hooks and stores
* State transitions
* Feature services (with mocked API client)
* Important user interactions

---

# 22. Architecture Rules

When adding or modifying code:

1. Follow this architecture.
2. Reuse existing components, hooks, and services.
3. Do not duplicate business logic.
4. Do not move code between layers without a clear reason.
5. Do not put business logic in presentational components.
6. Do not call the API directly from UI components.
7. Keep feature-specific logic inside its feature.
8. Keep shared components domain-independent.
9. Follow the import rules in section 13.
10. Avoid unnecessary abstractions.
11. Do not rewrite unrelated code.

---

# 23. Relationship With Other Documentation

```text
Architecture.md          → how the frontend code is structured
UI_Specification.md      → how the interface behaves and looks
Product_Specification.md → what the product does
Data_Model.md            → how application data is structured
State_Model.md           → how UI/application states transition
Development_Rules.md     → implementation constraints
```

Each document is the source of truth for its own domain.

If two documents conflict in an overlapping area, resolve it in this order:

1. Product Specification (what the product must do)
2. UI Specification (how it must look and behave)
3. Data Model / State Model
4. Architecture (how it is built)
5. Development Rules

Fix the lower-priority document so the conflict does not persist.