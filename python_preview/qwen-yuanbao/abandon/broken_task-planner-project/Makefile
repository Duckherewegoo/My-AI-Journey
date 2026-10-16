# ============================================================
# Task Planner — Makefile
# 常用命令一键执行
# ============================================================

.PHONY: help install dev install-dev lint format test eval clean docker-up docker-down

help: ## 显示帮助
	@echo "Task Planner — 可用命令:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

install: ## 安装运行时依赖
	pip install -e .

install-dev: ## 安装运行时 + 开发依赖
	pip install -e ".[dev]"

lint: ## 代码检查（ruff + pyright）
	ruff check task_planner tests
	pyright task_planner

format: ## 自动格式化代码
	black task_planner tests
	ruff check --fix task_planner tests

test: ## 跑单元测试（Mock 模式）
	USE_MOCK_LLM=true pytest tests/ -v

test-real: ## 跑集成测试（真实 LLM，需要 API Key）
	pytest tests/ -v -m "not mock"

eval: ## 跑 Agent 评估（真实 LLM）
	python -m tests.run_eval

cov: ## 测试覆盖率
	pytest tests/ --cov=task_planner --cov-report=html:tests/output/coverage

docker-up: ## 启动 Docker 服务
	docker compose --env-file .env up -d --build

docker-down: ## 停止 Docker 服务
	docker compose down

docker-logs: ## 查看日志
	docker compose logs -f app

clean: ## 清理缓存和构建产物
	find . -name "__pycache__" -exec rm -rf {} +
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
	rm -rf build/ dist/ *.egg-info/ .coverage htmlcov/ tests/output/
