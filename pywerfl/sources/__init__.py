"""One module per raw WERFL data source (e.g. designsafe). Each source module is
free to have its own folder layout, file formats, and instrumentation -- it just
needs to end by calling pywerfl.write_data.write_run() for each run, so every
source converges on the same format pywerfl.loader reads back."""
