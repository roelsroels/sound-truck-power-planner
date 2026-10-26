# Sound Truck Power Planner

Docker-ready electrical planning tool for mobile, high-output sound systems. Includes a SQLite equipment catalogue, a browser-based project editor and a preloaded two-infra/two-kick/one-top test rig.

**Engineering disclaimer:** This application provides provisional estimates only. Actual generator selection, cable sizes, earthing, protections and moving-vehicle approvals require validation by a qualified engineer.

Deployment: `cp .env.example .env && docker compose up -d --build`. Default binding: `127.0.0.1:8080`. Never commit private tokens.
