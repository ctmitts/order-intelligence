.PHONY: setup data db run docker clean

setup:        ## Create venv and install dependencies
	python3 -m venv .venv && ./.venv/bin/pip install -U pip && ./.venv/bin/pip install -r requirements.txt

data:         ## Regenerate anonymized data from data/orders_raw.csv
	./.venv/bin/python scripts/anonymize.py

db:           ## (Re)build the ChromaDB vector store from data/orders.csv
	./.venv/bin/python scripts/build_db.py

run:          ## Launch the Streamlit app
	./.venv/bin/streamlit run app/streamlit_app.py

docker:       ## Build and run the container
	docker build -t order-intelligence . && docker run -p 8501:8501 order-intelligence

clean:        ## Remove the built vector store
	rm -rf app/chroma_db
