# mafia-infiltration-legal-economy

## Installing dependencies and scraping the open data

The code comes with all the dependencies that can be installed from the requirements file. However, I recommend creating a virtual environment using a package manager like [Miniconda](https://docs.conda.io/en/latest/miniconda.html). To create a virtual environment and install the dependencies, run:

```bash
conda create -n mafia-infiltration python==3.11
conda activate mafia-infiltration
pip install -r requirements.txt
```

To execute the `scraper.py` script to download and process the open data, pass `input_filename (.xml)`, `output_filename (.csv)`, `status_filename (.csv)`, `log_file_path (.log)` in the following order, for example for 2023:

```bash
python scraper.py open_data/l190-2023.xml 2023.csv status_2023.csv log_2023.log
```
