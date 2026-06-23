# AI Study Assistant v2

Aplicatie locala pentru studiu pe baza documentelor tale.

## Ce face

- Ruleaza din folderul proiectului, fara cai hardcodate.
- Creeaza `documents/`, `storage/` si baza ChromaDB in folderul proiectului.
- Selecteaza documente prin dialog nativ Windows.
- Indexeaza PDF, DOCX si PPTX in ChromaDB.
- Raspunde exclusiv pe baza documentelor indexate.
- Afiseaza lista completa de documente indexate.
- Detecteaza intrebari despre un curs anume, de exemplu `despre ce este cursul 1`.
- Filtreaza retrieval-ul la documentul cerut cand intrebarea mentioneaza un curs/PDF.
- Pastreaza retrieval semantic global pentru intrebari de continut.
- Genereaza flashcards si quiz-uri interactive.
- Afiseaza un panou de diagnostics cu path-urile active.

## Structura

```text
ai-facultate-code/
  app.py
  requirements.txt
  install.ps1
  run_app.ps1
  START_AI_STUDY_ASSISTANT.bat
  README.md
  documents/
  storage/
```

## Instalare pe orice PC Windows

1. Instaleaza Python 3.12 sau 3.11. Nu folosi Python 3.14 pentru acest proiect.
2. Instaleaza Ollama.
3. Descarca modelele in Ollama:

```powershell
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

4. Deschide PowerShell in folderul proiectului.
5. Ruleaza:

```powershell
.\install.ps1
```

Scriptul creeaza `.venv` local si instaleaza dependintele.

Daca ai mai multe versiuni Python instalate, `install.ps1` alege automat Python 3.12 sau 3.11. Optional, poti indica explicit executabilul:

```powershell
$env:PYTHON_EXE = "C:\Path\To\Python312\python.exe"
.\install.ps1
```

## Pornire

Varianta simpla:

```text
Dublu click pe START_AI_STUDY_ASSISTANT.bat
```

Varianta PowerShell:

```powershell
.\run_app.ps1
```

Scriptul porneste aplicatia din folderul curent al proiectului. Daca portul `8501` este ocupat, foloseste urmatorul port liber pana la `8510`.

## Documente si baza de date

Folderul implicit pentru documente este:

```text
documents/
```

Baza ChromaDB este salvata local in:

```text
storage/chroma/
```

Fisierul colectiei active este:

```text
storage/active_collection.txt
```

Toate aceste path-uri sunt relative la folderul proiectului.

## Verificare in aplicatie

In sidebar, sectiunea `Diagnostics` arata:

- Current project root
- Current storage folder
- Current documents folder
- Current database path
- Active collection

In partea de sus a aplicatiei apare si `Proiect activ`, ca sa vezi exact din ce folder ruleaza.

## Exemple

Intrebare despre un document anume:

```text
despre ce este cursul 1
rezumat cursul 3
ce contine cursul 5
```

Intrebari globale de continut:

```text
ce este energia interna
explica difractia
```

Intrebari despre inventar:

```text
ce cursuri am indexat?
ce documente sunt indexate?
```

## Mutare pe alt PC

Copiaza tot folderul proiectului pe noul PC, apoi ruleaza:

```powershell
.\install.ps1
.\run_app.ps1
```

Nu trebuie modificat niciun path in cod.
