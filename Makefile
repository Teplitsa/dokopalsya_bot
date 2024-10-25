.PHONY: docker-run

run:
	docker build -t factchecker . && docker run -it --env-file .env factchecker

