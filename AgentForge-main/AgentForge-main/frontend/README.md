# AgentForge Frontend

[![Next.js 16](https://img.shields.io/badge/Next.js-16-black?logo=next.js&logoColor=white)](package.json)
[![React 19](https://img.shields.io/badge/React-19-149ECA?logo=react&logoColor=white)](package.json)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](tsconfig.json)
[![Tailwind CSS v4](https://img.shields.io/badge/Tailwind_CSS-v4-06B6D4?logo=tailwindcss&logoColor=white)](package.json)

The Next.js client for AgentForge: a real-time workspace for watching and steering the multi-agent pipeline. It provides a project dashboard, a per-project chat interface, a repository explorer with an editable Monaco-based code viewer, an MCP management console, and a reliability dashboard, all backed by the FastAPI service in `../backend` over REST and Server-Sent Events.

- **Live app:** [frontend-naman-213.vercel.app](https://frontend-naman-213.vercel.app)
- **Architecture docs:** [Frontend_Design.md](../docs/Frontend_Design.md)
- **Deployment docs:** [Deployment.md](../docs/Deployment.md)

## Stack

| Layer | Choice |
|---|---|
| Framework | Next.js 16 (App Router, Turbopack), React 19, TypeScript |
| Styling | Tailwind CSS v4, shadcn/ui on Radix primitives, `@tailwindcss/typography` for rendered Markdown |
| Server data | TanStack Query against the REST API |
| Live data | Native `EventSource` against the SSE endpoint, no client library |
| Editor | Monaco (`@monaco-editor/react`), dynamically imported client-side |
| Motion | Framer Motion |
| Markdown | `react-markdown` with `remark-gfm` |
| Icons | Lucide |

## Getting started

```powershell
npm install
copy .env.example .env.local
npm run dev
```

The app runs at `http://localhost:3000` and expects a backend reachable at `NEXT_PUBLIC_API_URL`. See the root [README](../README.md) for backend setup. `src/lib/api.ts` is the single source every API call and SSE connection resolves that URL from; there is no other place a backend URL is configured.

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Start the development server (Turbopack) |
| `npm run build` | Create a production build |
| `npm run start` | Serve a production build |
| `npm run lint` | Run ESLint |
| `npx tsc --noEmit` | Type-check without emitting output |

## Project structure

| Path | Contents |
|---|---|
| `src/app/` | Routes: dashboard, login, `/mcp`, `/reliability`, `/projects/[projectId]`, `/runs/[runId]` |
| `src/components/dashboard/` | Project list, filters, pagination, create-project form |
| `src/components/workspace/` | The per-project tabbed workspace: chat, repository, activity, docs, knowledge |
| `src/components/chat/` | Conversation UI, composer, live status |
| `src/components/repo/` | File tree, Monaco editor, tabs, quick-open, Markdown preview |
| `src/components/run/` | Agent pipeline visualization, event feed, recovery panel |
| `src/components/mcp/` | MCP server list and tool explorer |
| `src/components/reliability/` | Failure-rate and recovery-analytics dashboard |
| `src/components/providers/` | Auth context, TanStack Query provider |
| `src/components/shell/` | App shell and route gating |
| `src/components/ui/` | shadcn/ui primitives |
| `src/hooks/` | Shared SSE connection, live status derivation, persisted UI state |
| `src/lib/` | `api.ts` (all backend calls), `types.ts`, `auth-storage.ts`, `utils.ts` |

Every route other than `/login` requires authentication. `components/providers/auth-provider.tsx` owns the session; `components/shell/app-shell.tsx` redirects unauthenticated visitors and attaches the stored JWT to every request.

## Configuration

The only environment variable this app reads is `NEXT_PUBLIC_API_URL`, documented in [`.env.example`](.env.example). All other behavior, including theming, is defined in code rather than through configuration.

## Learn more

This project was originally scaffolded with `create-next-app`. For framework-level questions not specific to this codebase, see the [Next.js documentation](https://nextjs.org/docs).
