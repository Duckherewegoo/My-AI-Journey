.PHONY: format lint test eval docker-restart docker-logs docker-rebuild docker-up docker-down clean

format:
	black src tests
	isort src tests

lint:
	ruff check src tests
	pyright src

test:
	USE_MOCK_LLM=true pytest tests/ -v --tb=short

eval:
	USE_MOCK_LLM=false python -m tests.harness.run_eval

docker-restart:
	docker compose down && docker compose up -d --build 

docker-logs:
	docker logs -f task_planner_app

docker-rebuild:
	docker compose down -v && docker compose build --no-cache && docker compose up -d && docker logs -f task_planner_app

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf *.egg-info dist build
	rm -rf tests/output/*.json tests/output/*.md 2>/dev/null || true
