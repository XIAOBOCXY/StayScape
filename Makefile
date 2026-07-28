PYTHON := .venv/Scripts/python.exe

install:
	python -m venv .venv
	$(PYTHON) -m pip install -r apps/server/requirements.txt
	npm --prefix apps/web install --cache apps/web/.npm-cache

test:
	$(PYTHON) -m pytest apps/server/tests -q

lint:
	$(PYTHON) -m compileall -q apps/server/app
	npm --prefix apps/web run build

seed:
	$(PYTHON) scripts/seed_demo.py

reset-demo:
	$(PYTHON) scripts/reset_demo.py

migrate:
	$(PYTHON) -m alembic -c apps/server/alembic.ini upgrade head

skills:
	$(PYTHON) scripts/package_skills.py

dev:
	$(PYTHON) -m uvicorn app.main:app --app-dir apps/server --reload --host 0.0.0.0 --port 8000

dev-web:
	npm --prefix apps/web run dev

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

