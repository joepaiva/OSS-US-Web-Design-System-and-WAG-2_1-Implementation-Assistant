# Human Testing Guide

This guide walks you through setting up and testing the application locally using Docker Desktop.

## Prerequisites

### Install Docker Desktop

**macOS:**
1. Download Docker Desktop from https://www.docker.com/products/docker-desktop/
2. Open the downloaded `.dmg` file and drag Docker to Applications
3. Launch Docker Desktop from Applications
4. Wait for Docker to finish starting (whale icon in menu bar stops animating)

**Windows:**
1. Download Docker Desktop from https://www.docker.com/products/docker-desktop/
2. Run the installer (requires WSL 2 backend)
3. Follow the installation wizard
4. Restart your computer if prompted
5. Launch Docker Desktop from the Start menu

**Linux (Ubuntu/Debian):**
```bash
sudo apt-get update
sudo apt-get install docker.io docker-compose-plugin
sudo systemctl start docker
sudo usermod -aG docker $USER
# Log out and log back in for group changes to take effect
```

## Before You Start: Create Your Secrets

The application will **refuse to start** until you supply its secrets, and it will
name the one it is missing. This is deliberate (AB-FR-612): earlier versions
shipped with a working placeholder JWT secret and an all-zero encryption key, so
the application started and ran — signing your sessions and encrypting your
multi-factor seeds with values published in this repository.

1. Copy the template: `cp .env.example .env`
2. Open `.env` and fill in every empty value. Each one has the command that
   generates it in the comment above it — mostly `openssl rand -hex 32`.
3. Use a **different** value for each key. They are separate so that compromising
   one does not expose the others.

Keep `.env` out of version control. It holds real credentials.

## Starting the Application

1. Open a terminal and navigate to the project directory
2. Run:
   ```bash
   docker compose up --build
   ```
   If it stops with `required variable ... is missing a value`, that is the
   check above doing its job: fill that variable in `.env` and run again. It
   reports one at a time, so filling in all of `.env.example` up front is
   quicker than going round the loop.
3. Wait for the output to show the application is ready
4. Open your browser at the port the `ports:` line of `docker-compose.yml`
   publishes — `8080` for the Go and .NET chassis, `8000` for Python and Node.js

## Creating Your First Account

1. Navigate to http://localhost:8081/register.html
2. Fill in:
   - **Name:** Your name
   - **Email:** Your email address
   - **Password:** A password (minimum 8 characters)
3. Click "Register"
4. You should be redirected to the login page

## Logging In

1. Navigate to http://localhost:8081/login.html
2. Enter your email and password
3. Click "Login"
4. You should be redirected to the dashboard

## Troubleshooting

### "Cannot connect to the Docker daemon"
- Make sure Docker Desktop is running (check the system tray/menu bar)

### "Port 8081 already in use"
- Change the port: `APP_PORT=9090 docker compose up`
- Or stop whatever is using port 8081

### "Database connection refused"
- Wait a few seconds — the database takes a moment to initialize
- Try: `docker compose down && docker compose up`

### Resetting All Data
To completely reset the application and database:
```bash
docker compose down -v
docker compose up
```
The `-v` flag removes the database volume, deleting all data.

## Creating an Admin Account

The first registered user has standard permissions. To create an admin:

1. Register a new account through the web interface
2. Access the database:
   ```bash
   docker compose exec db psql -U app_user -d app_db
   ```
3. Update the user role:
   ```sql
   UPDATE users SET role = 'platform_admin' WHERE email = 'your-email@example.com';
   ```
4. Log out and log back in for the role change to take effect

## Stopping the Application

Press `Ctrl+C` in the terminal where docker compose is running, or:
```bash
docker compose down
```
