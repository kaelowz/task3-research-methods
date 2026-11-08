.PHONY: all convert process figures notebook clean
all: convert process figures notebook

convert:    ## CSV -> JSONL (lossless)
	python -m src.convert_raw

process:
	python -m src.process_data

figures:
	python -m src.visualize

notebook:
	jupyter nbconvert --to notebook --execute --inplace notebooks/01_data_analysis.ipynb

clean:
	rm -rf reports/figures/* data/processed/*.csv .ipynb_checkpoints __pycache__
