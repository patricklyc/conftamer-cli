# ParamTrack example artifacts

These files are real outputs from ParamTrack and its gopls CType analysis for
Prometheus. They are organized by producer stage and test run; generated graph
or PMGraph outputs should not be written back into this directory.

## Layout

```text
paramtrack/
├── static/
│   ├── unmarshaler_subgraph.text
│   ├── unmarshaler_subgraph.gv
│   ├── accessors.text
│   ├── accessors.gv
│   └── gopls.log
└── runs/
    ├── target-scraper-all/
    │   ├── parameters.csv
    │   └── parameters_hierarchy.txt
    └── manager-st-zero/
        ├── parameters.csv
        ├── parameters_hierarchy.txt
        └── paramtrack.log
```

The CType prefix stripped from module-local names in these artifacts is:

```text
github.com/prometheus/prometheus
```

## Static analysis

`static/unmarshaler_subgraph.text` and `static/accessors.text` are the current
machine-readable CType graphs. Each is one JSON document containing `Edges`,
`Vertices`, and `List`.

| Graph | Vertices | Edges | Name mappings | Nonidentity aliases |
|---|---:|---:|---:|---:|
| Unmarshaler Subgraph | 57 | 90 | 58 | 1 |
| Accessors | 582 | 822 | 595 | 13 |

The `.gv` files are topology-only Graphviz renderings. `gopls.log` is the
producer log. They are retained for inspection but are not machine inputs to
the rewritten tool34.

## Target-scraper run

`runs/target-scraper-all/parameters.csv` contains one ParamTrack row:

```text
API=Prometheus, Verb=GET, Resource=<empty>, CType=/scrape.targetScraper
```

The row contains 108 sorted, unique parameter keys. Its empty resource
normalizes to `/` when compared with ContextTrack HTTP paths.

`parameters_hierarchy.txt` is the corresponding human-readable parameter-tree
view and is not a tool34 input.

## Manager ST-zero run

`runs/manager-st-zero/parameters.csv` contains four rows for the same message:

```text
API=Prometheus, Verb=GET, Resource=/metrics
```

| CType | Parameter keys |
|---|---:|
| `/scrape.scrapeLoop` | 133 |
| `/discovery.Manager` | 120 |
| `/scrape.Manager` | 201 |
| `/scrape.targetScraper` | 108 |

The four sets contain 226 unique parameter keys in total. All four CTypes are
represented in the Accessors graph and not in the Unmarshaler Subgraph.

`paramtrack.log` records the associated Delve run. The selected test was:

```text
TestManagerSTZeroIngestion/format=PrometheusProto/withST=false/stZeroIngest=false
```

`parameters_hierarchy.txt` and `paramtrack.log` are reference artifacts, not
tool34 machine inputs.

## Machine inputs

The rewritten tool34 targets these files directly:

- `static/unmarshaler_subgraph.text`;
- `static/accessors.text`; and
- a selected `runs/*/parameters.csv`.

Future gopls GraphML files belong under `static/` beside their equivalent
`.text` graphs. Their exact input contract must be based on real producer
output rather than inferred from the Graphviz files.
