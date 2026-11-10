# DueGuide Recovery — Frontend (React + Vite + AG Grid)

This is the frontend application for **DueGuide**, an AI-powered recovery engine built for the PayPal AI Hackathon 2026. 

The interface enables merchants to review overdue invoices, generate AI-assisted payment proposals, approve alternatives, and track the entire negotiation and execution lifecycle in a real-time AG Grid audit trail.

## 🏗️ Tech Stack
- **Framework:** React 18 + TypeScript + Vite
- **Grid Engine:** AG Grid Community v31.3.4
- **Routing:** React Router v6
- **Styling:** Custom CSS (Fintech / Dark mode)
- **API Client:** Native Fetch (centralized in `src/api/client.ts`)

## 🚀 Getting Started (Setup for New Machines)

Follow these steps to run the frontend locally on a clean machine.

### 1. Prerequisites
- **Node.js**: `v20.14.0` or higher (Recommended: `v20.19.0+` if using the latest Vite versions, but `v20.14` works with the pinned Vite 5 version in this repo).
- **NPM**: v10 or higher.
- **Backend API**: The FastAPI backend must be running locally (usually at `http://127.0.0.1:8000`).

### 2. Installation
Navigate to the `ui/` folder and install the dependencies. 
*(Note: The dependencies are pinned in `package.json` to ensure AG Grid v31 and React 18 compatibility).*

```bash
cd ui
npm install