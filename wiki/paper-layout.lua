-- Export presentation only: canonical prose, captions and values stay in Markdown.
-- Pandoc 2.14 emits longtable, which cannot run inside a two-column article.
-- Assign wrapping columns; build.py turns the generated table into a float.
function Table(tbl)
  local columns = #tbl.colspecs
  local weights = {
    [2] = {0.30, 0.70},
    [4] = {0.20, 0.26, 0.33, 0.21},
    [6] = {0.12, 0.29, 0.17, 0.10, 0.16, 0.16},
    [7] = {0.24, 0.08, 0.15, 0.17, 0.12, 0.12, 0.12},
  }
  for i = 1, columns do
    tbl.colspecs[i] = {pandoc.AlignLeft, weights[columns] and weights[columns][i] or 1 / columns}
  end
  return tbl
end
