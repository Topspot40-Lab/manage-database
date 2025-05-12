# TopSpot Program Tech Stack

Your TopSpot solution is composed of two main programs:

1. **Track Generation & Importer**  
   - A Python utility that:
     - Fetches top-track data and descriptions from XAI and Spotify APIs.  
     - Generates JSON files containing track metadata, artwork links, and descriptions.  
     - Verifies Spotify track IDs and ensures data integrity.  
     - Imports validated JSON into the **Supabase Postgres** database.

2. **End-User Interface**  
   - A Svelte-based frontend (Svelte 5 / SvelteKit) using HTML, CSS, TypeScript, and JavaScript.  
   - Communicates with the backend via REST endpoints for:
     - Fetching and playing tracks.  
     - User login/authentication and payment workflows (Stripe).  
     - Generating or retrieving TTS audio for intros/details.

---

## Tech Stack Layers

| Layer                 | Role                                           | Technologies / Tools                                         |
|-----------------------|------------------------------------------------|--------------------------------------------------------------|
| **Presentation**      | The UI your end users interact with            | Svelte 5 / SvelteKit; Tailwind CSS; HTML/CSS/TypeScript/JavaScript |
| **Application**       | Your backend logic & APIs                      | Python 3.12+; FastAPI; Uvicorn; Spotipy; XAI integration; SQLAlchemy/SQLModel; Pydantic; Supabase-py (Auth & Stripe); Alembic |
| **Data**              | Where your app’s data lives                    | PostgreSQL (two instances: Supabase-managed for users/payments/auth; TopSpot DB for tracks/playlists); JSON files for import/export |
| **Dev & Ops**         | CI/CD, versioning, containerization, hosting   | Git/GitHub; Docker Desktop (containers for FastAPI services and local Supabase sandbox); Supabase services (Auth, Billing, Storage, Realtime); Bluehost; Render/Vercel |
| **Extras**            | Specialized features                           | Text-to-Speech (pyttsx3; external TTS APIs; Supabase Edge Functions); Storage buckets for artwork & TTS files; Stripe integration |

---

## How the stack is “defined”:

1. **Programs**  
   - **Track Generation & Importer** handles data acquisition, JSON file creation, validation, and import into Supabase Postgres.  
   - **End-User Interface** is the Svelte front-end that consumes backend endpoints for playback, authentication, and payments.

2. **Presentation (Client-Side):**  
   - SvelteKit builds a fast, reactive SPA/SSR app.  
   - Tailwind CSS and TypeScript ensure type safety and consistent styling.
3. **Application (Server-Side):**  
   - FastAPI routes handle JSON import, playback endpoints, auth (via Supabase JWT), and Stripe payments.  
   - Business logic for track verification, TTS generation, and user session management lives here.
4. **Data (Persistence):**  
   - **Supabase Postgres**: stores `auth.*` tables (users, profiles) and Stripe billing tables.  
   - **TopSpot DB**: stores tracks, artists, playlists, and other domain tables.  
   - JSON serves as both seed and backup for track data.
5. **Dev & Ops:**  
   - Docker composes the FastAPI backend and a local Supabase instance via `npx supabase start`.  
   - CI/CD builds and deploys containers to platforms like Render or Vercel; static assets can reside on Bluehost.
6. **Extras:**  
   - TTS may run server-side or via Supabase Edge Functions.  
   - Supabase Storage provides secure hosting for media assets, served via CDN.

By structuring it this way, you clearly separate concerns: data ingestion vs. user interaction, while leveraging Supabase for auth and payments and Docker for consistent environments.
