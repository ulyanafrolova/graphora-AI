# Graphora — wizja

Agenci AI piszą kod szybciej, niż ludzie są w stanie go zrozumieć. Graphora daje ludziom i agentom weryfikowalną mapę kodu.

## Dlaczego Graphora

### Wąskim gardłem jest teraz review

Większość kodu piszą dziś agenci, a ludzie coraz więcej czasu poświęcają na przeglądanie kodu, którego nie napisali. Kluczowe staje się ustalenie, co zepsuje dana zmiana, a agenci czatowi odpowiadają na to tekstem, który trzeba ponownie sprawdzać.

### Powtarzalne fakty zamiast jednorazowych odpowiedzi

Agenci programistyczni za każdym razem badają repozytorium od zera, a ich odpowiedzi mogą się różnić między uruchomieniami. Graphora buduje graf deterministycznie: ten sam commit zawsze daje ten sam graf, który można zapisać, porównać między commitami i dołączyć do review. Zależności, cykle i zasięg zmian są obliczane przez algorytmy, a nie zgadywane.

### Lepsi agenci, a nie kolejny agent

Zapytania do grafu (zależności odwrotne, zasięg zmian, cykle, sąsiedzi) są udostępniane jako serwer MCP, dzięki czemu Claude Code, Cursor i inni agenci mogą korzystać z Graphory jako narzędzia. Nasi agenci są demonstracją; produktem jest strukturalna pamięć o kodzie, z której może korzystać każdy agent.

## Funkcje

### Struktura i architektura

Most frontend ↔ backend. Łączy trasy w Pythonie z wywołaniami HTTP w TypeScripcie krawędzią oznaczoną jako heurystyczna i pokazuje pełną ścieżkę od przycisku w UI do bazy danych.

Automatyczne komponenty. Klasteryzacja algorytmem Louvain grupuje pliki w komponenty, agent nadaje im nazwy, a mapę można przybliżać od poziomu systemu przez komponent i plik do symbolu.

Rozrywanie cykli. Algorytm znajduje minimalny zbiór krawędzi do usunięcia (feedback arc set), a agent podpowiada, jak to zrobić. Tylko rekomendacje, bez automatycznego refaktoringu.

### AI i agenci

GraphRAG. Lokalne embeddingi funkcji i klas pozwalają wyszukiwać kod po znaczeniu, a sąsiedzi w grafie dają agentowi powiązany kontekst zamiast przypadkowych fragmentów.

Weryfikacja pull requestów od AI. Graphora porównuje graf przed zmianą i po niej i pokazuje, gdzie opis PR nie zgadza się z faktycznymi zmianami.

Benchmark. 30 pytań ze znanymi odpowiedziami porównuje ten sam model z samym grepem i z Graphorą przez MCP: trafność, halucynacje, tokeny i czas.

Zapytania do grafu w języku naturalnym. LLM tłumaczy prośbę na formalne zapytanie do grafu, a wykonuje je kod, więc wynik jest dokładny.

### Bezpieczeństwo

Mapa powierzchni ataku. Ścieżki od endpointów HTTP do niebezpiecznych wywołań, takich jak eval, subprocess czy surowy SQL, podświetlone na grafie.

Osiągalność podatnych zależności. Znane podatności z OSV.dev są sprawdzane względem grafu, aby pokazać, które z nich są faktycznie osiągalne z kodu.

### Inżynieria

Testy do uruchomienia. Graf pokazuje, które pliki testowe zależą od zmienionego modułu.

Tryb na żywo. Przyrostowe parsowanie Tree-sitter aktualizuje graf przy każdym zapisie pliku.

## Trudne pytania

#### Po co Graphora, skoro istnieją Claude Code i Cursor?

Odpowiadają tekstem, który trzeba ponownie sprawdzać. Graphora daje obliczony graf, powtarzalny dla każdego commita, z którego ci sami agenci mogą korzystać przez MCP.

#### A co z DeepWiki?

DeepWiki generuje dokumentację za pomocą LLM: to opis, a nie weryfikowalny graf. Działa w chmurze i tylko dla publicznych repozytoriów. Graphora daje deterministyczne fakty, działa lokalnie i wskazuje dowody.

#### Modele są coraz mądrzejsze. Czy Graphora się zdezaktualizuje?

Im więcej kodu piszą agenci, tym ważniejsza jest niezależna weryfikacja, która nie zależy od LLM. Graf nie halucynuje, niezależnie od tego, jak mocny jest model.

#### Po co własni agenci, skoro Graphora jest infrastrukturą?

To projekt zaliczeniowy z przedmiotu o agentach AI. Pokazuje, jak agenci weryfikujący dowody działają na deterministycznych narzędziach, a ten sam wzorzec sprawdza się dla każdego zewnętrznego agenta.

#### Czy mały lokalny model nie jest za słaby?

Właśnie dlatego graf jest ważny: fakty oblicza algorytm, a mały model jedynie formułuje odpowiedź. Wszystko działa offline, bez wysyłania kodu do chmury.
