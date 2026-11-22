# Deploying ClinicFlow to alwaysdata (free)

One site: Django serves the API, the admin and the built React app from a single address,
e.g. `https://YOUR-ACCOUNT.alwaysdata.net`. Synthetic data only.

**What I checked:** alwaysdata's Python docs say a Python site is created under *Web → Sites* with type
**Python WSGI**, an application path, and optional working directory, environment variables, Python version
and virtualenv directory. Python runs behind uWSGI, with logs in `~/admin/logs/uwsgi/<site-id>.log`.
**What I tested on my machine:** the whole site in production mode behind gunicorn; the test suite on the
PyMySQL driver; and the full suite plus direct attempts to break each database rule on **MariaDB 10.11**.
alwaysdata's database is MariaDB (MySQL 8.0 is only on their private plans); it offers 10.6, 10.11, 11.4 and 11.8,
so pick 10.11 if the panel lets you choose. **What I could not verify:** alwaysdata's exact panel labels, which Python
versions it offers, whether `git` is installed on the server, and the exact database size limit. If the panel differs from the
steps below, follow the panel and keep the intent.

## 1. Before you start
- The project is pushed to GitHub (see README).
- `backend/spa/` exists in the repo (the built React app). After any frontend change, rebuild it:
  `cd frontend && npm run build`, then commit `backend/spa`.

## 2. Create the account and database
1. Create a free account at alwaysdata.com. Your account name becomes `ACCOUNT.alwaysdata.net`.
2. In the panel, open **Databases → MySQL**. alwaysdata's docs say a default user (named after your account) and database
   (their examples use `ACCOUNT_base`) are created with the account; you can use those or create new ones.
   Copy the exact database name, user name and host from the panel. The host is `mysql-ACCOUNT.alwaysdata.net`, port 3306.
   (If your account name is long, MySQL users get an ID instead; check *Databases → MySQL → Users*.)

## 3. Get the code onto the server
Enable SSH for your account in the panel, then connect (Windows 10/11 has `ssh` built in):
```
ssh ACCOUNT@ssh-ACCOUNT.alwaysdata.net
```
On the server:
```
python --version            # Django 5.2 needs 3.10 or newer; if lower, prefix commands with PYTHON_VERSION=3.12
git clone https://github.com/YOUR-USERNAME/clinicflow.git
python -m venv ~/clinicflow/venv
~/clinicflow/venv/bin/pip install -r ~/clinicflow/backend/requirements-alwaysdata.txt
```
If `git` is missing, upload the project folder with SFTP instead. `requirements-alwaysdata.txt` uses the pure-Python
PyMySQL driver so nothing has to be compiled.

## 4. Configure the site (Web → Sites → your site → edit)
| Field | Value |
|---|---|
| Type | Python WSGI |
| Application path | `/clinicflow/backend/config/wsgi.py` |
| Working directory | `/clinicflow/backend` |
| Virtualenv directory | `/clinicflow/venv/` |
| Python version | the same one you used for the venv |
| Environment variables | see below, one per line |

Paths are relative to your home directory (a community guide for alwaysdata uses `/www/wsgi.py` for `~/www/wsgi.py`).

```
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=<a long random string>
DJANGO_ALLOWED_HOSTS=ACCOUNT.alwaysdata.net
CSRF_TRUSTED_ORIGINS=https://ACCOUNT.alwaysdata.net
DB_NAME=<from the panel>
DB_USER=<from the panel>
DB_PASSWORD=<your database password>
DB_HOST=<from the panel>
DEMO_MODE=1
```
Make a secret key with: `python -c "import secrets; print(secrets.token_urlsafe(50))"`.
`DEMO_MODE=1` makes today's appointment list fill itself with a demo schedule when it is empty, so the site never
looks dead. Leave it off for anything with real data.

## 5. Create the tables and demo data (on the server)
The command line does not see the site's environment variables, so export the same ones first:
```
cd ~/clinicflow/backend
export DJANGO_DEBUG=0 DJANGO_SECRET_KEY=... DJANGO_ALLOWED_HOSTS=ACCOUNT.alwaysdata.net \
       DB_NAME=... DB_USER=... DB_PASSWORD=... DB_HOST=...
PY=~/clinicflow/venv/bin/python
$PY manage.py migrate
$PY manage.py createsuperuser
$PY manage.py seed --appointments 30000 --patients 6000 --doctors 12
$PY manage.py setup_demo_users --password CHOOSE-A-DEMO-PASSWORD
$PY manage.py collectstatic --noinput
```
That is roughly 20 MB of database, well under the free plan's limit as far as I could tell. If `seed` is killed for lack of memory,
lower `--appointments`. Then **restart the site** in the panel and open your address.

## 6. Sign in
- Admin (dashboard): your superuser. **Never publish these credentials.**
- Receptionist: `reception1`. Doctor: `doctor1` ... `doctor12`. Password: the demo password you chose.
Put the receptionist and one doctor login (not admin) in the README for visitors.

## Updating later
```
cd ~/clinicflow && git pull
~/clinicflow/venv/bin/pip install -r backend/requirements-alwaysdata.txt
cd backend && $PY manage.py migrate && $PY manage.py collectstatic --noinput
```
then restart the site in the panel.

## If something is wrong
| Symptom | Likely cause |
|---|---|
| "Bad Request (400)" | `DJANGO_ALLOWED_HOSTS` does not match the address you opened |
| "CSRF verification failed" or login errors | `CSRF_TRUSTED_ORIGINS` must be `https://...` and match exactly |
| Blank page or Django 404 on `/` | `backend/spa` was not committed or pulled; rebuild and push it |
| "Server error (500)" | Read `~/admin/logs/uwsgi/<site-id>.log` |
| Database errors | Re-check `DB_*` values against the panel |
| First load is slow | Free plan, 256 MB RAM; later requests are faster |
