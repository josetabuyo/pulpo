#!/usr/bin/env bash
# Borra todos los archivos generados del pipeline. Preserva fuentes originales.
# Fuentes = *.png que NO terminan en _annotated/_cropped, y *.jpg originales.
ASSETS="$(dirname "$0")/assets"
find "$ASSETS" -type f \( \
  -name "*_annotated.png" \
  -o -name "*_cropped.png" \
  -o -name "*_bubbles.json" \
  -o -name "*_pipeline_result.json" \
  -o -name "*_click_points.png" \
  -o -name "after_click_*.png" \
  -o -name "current.png" \
  -o -name "debug_*.png" \
  -o -name "bottom_check.png" \
\) -delete
echo "assets/ limpio"
