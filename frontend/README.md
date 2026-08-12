# PITWALL frontend

React + TypeScript + Vite. The interface only renders what the API measured — every number on
screen comes from `/api/session`, and nothing is derived client-side.

See the [root README](../README.md) for what the project does, how it was verified, and how to run
it. In development the API is expected on `http://localhost:8000`; in a built deployment the backend
serves this bundle from the same origin.

```powershell
npm run dev     # http://localhost:5173
npm run build   # emits dist/, which the backend serves
```
