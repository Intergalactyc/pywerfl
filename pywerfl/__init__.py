"""PyWERFL -- tools for working with data from the TTU Wind Engineering Research
Field Laboratory (WERFL), potentially from multiple data sources.

    pywerfl.sources.*  -- one module per raw data source (e.g. designsafe), each
                           ingesting that source's own layout/format and ending by
                           calling pywerfl.write_data.write_run() per run
    pywerfl.write_data  -- shared writer for the analysis-ready format
    pywerfl.loader       -- shared reader for the analysis-ready format; this is
                           what analysis code should import
"""
