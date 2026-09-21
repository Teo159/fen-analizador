# FEN Analizador — versión web

Esta carpeta está preparada para publicar el analizador como una aplicación web con Streamlit.

## Publicación
1. Crea un repositorio en GitHub.
2. Sube `app.py`, `requirements_web.txt` y opcionalmente `DATOS.xlsx`.
3. En Streamlit Community Cloud selecciona el repositorio, rama y archivo `app.py`.
4. La aplicación quedará disponible mediante una URL pública de Streamlit.

## Uso
El usuario podrá cargar su propio Excel desde el navegador. No necesita instalar Python.

## Formato esperado
- `C y E`: `year`, `month`, `E_index`, `C_index`
- `MEI`, `PDO`, `SOI`: primera columna `year` y luego meses.

## Nota científica
Los umbrales y detección de eventos son exploratorios. Para una publicación académica se deben validar las definiciones de C y E y la metodología oficial de clasificación de ENSO/FEN que se adopte.
