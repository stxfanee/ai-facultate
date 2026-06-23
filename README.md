# AI Study Assistant v2

Aplicatie locala pentru studiu pe baza documentelor tale.

## Ce face v2

- Selecteaza documente prin dialog nativ Windows.
- Indexeaza PDF, DOCX si PPTX in ChromaDB.
- Salveaza baza local in `storage/chroma`.
- Raspunde exclusiv pe baza documentelor indexate.
- Afiseaza sursele folosite.
- Compara idei intre mai multe cursuri.
- Genereaza flashcards.
- Genereaza quiz-uri interactive.
- Permite alegerea unui model Ollama mai puternic, de exemplu `qwen3:14b`, daca este instalat.
- Se poate porni prin dublu click pe `START_AI_STUDY_ASSISTANT.bat`.

## Structura proiectului

```text
ai/
  app.py
  requirements.txt
  install.ps1
  run_app.ps1
  START_AI_STUDY_ASSISTANT.bat
  README.md
  documents/
  storage/
```

## Fisiere

`app.py`

Aplicatia principala Streamlit. Contine interfata, selectorul Windows, indexarea, intrebarile, comparatiile, flashcardurile si quiz-ul.

`requirements.txt`

Lista bibliotecilor Python necesare.

`install.ps1`

Instaleaza mediul virtual `.venv` si dependintele.

`run_app.ps1`

Porneste aplicatia Streamlit.

`START_AI_STUDY_ASSISTANT.bat`

Launcher pentru dublu click.

`documents/`

Folder optional pentru documente de test.

`storage/`

Folderul unde ChromaDB salveaza indexul local.

## Instalare

Din PowerShell:

```powershell
cd C:\Users\stefa\OneDrive\Documents\ai
.\install.ps1
```

Comanda creeaza `.venv` si instaleaza toate bibliotecile din `requirements.txt`.

## Pornire

Varianta cea mai simpla:

```text
Dublu click pe START_AI_STUDY_ASSISTANT.bat
```

Varianta din PowerShell:

```powershell
.\run_app.ps1
```

Aplicatia se deschide la:

```text
http://localhost:8501
```

## Modele Ollama

Modelul actual instalat si verificat local este:

```text
qwen3:8b
```

Pentru un model mai inteligent, v2 stie sa foloseasca:

```text
qwen3:14b
```

Daca `qwen3:14b` nu este instalat, il poti selecta in aplicatie si apasa `Descarca modelul ales`.

Modelul pentru embeddings ramane:

```text
nomic-embed-text
```

## Flux de lucru

1. Porneste aplicatia.
2. In bara din stanga apasa `Alege folder` sau `Alege fisiere`.
3. Selecteaza PDF, DOCX sau PPTX.
4. Apasa `Indexeaza selectia`.
5. Foloseste taburile:
   - `Intrebari`
   - `Legaturi intre cursuri`
   - `Flashcards`
   - `Quiz`

## Observatii

- Totul ruleaza local.
- Documentele nu sunt trimise in cloud.
- Raspunsurile sunt limitate la documentele indexate.
- Selectorul Windows apare doar cand aplicatia ruleaza pe calculatorul tau, nu pe un server remote.
