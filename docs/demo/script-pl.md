# Graphora — scenariusz prezentacji

## Problem

Coraz więcej kodu piszą agenci AI, a człowiek musi go przejrzeć i zatwierdzić. Przed każdą zmianą trzeba wiedzieć, które moduły od niej zależą, a w projekcie z tysiącami plików nie da się tego sprawdzić ręcznie. Cursor czy Claude Code odpowiadają na takie pytanie tekstem bez dowodów: odpowiedź może być błędna, a przy kolejnym pytaniu inna.

## Rozwiązanie i rola AI

Graphora buduje graf zależności kodu algorytmicznie, bez AI, a każda krawędź wskazuje plik, linię i commit, z którego pochodzi. Graf jest dokładny, ale nie rozumie pytań w języku naturalnym i nie wie, które z tysięcy węzłów są ważne dla danego pytania. AI zamienia pytanie na zapytania do grafu, wybiera istotne wyniki i wyjaśnia je. Każdą odpowiedź AI sprawdzamy na grafie, więc model nie może podać zależności, której nie ma w kodzie.

## Co robi system

Wejście to link do repozytorium GitHub lub plik ZIP. Wyjście to interaktywna mapa zależności z zaznaczonymi cyklami i plikami najbardziej ryzykownymi przy zmianach. Na pytanie „Co się zepsuje, jeśli zmienię AuthService?” system zwraca listę zależnych plików z numerami linii i podświetla je na mapie. Te same zapytania udostępniamy przez MCP, więc Claude Code i Cursor mogą korzystać z grafu zamiast przeszukiwać repozytorium. Całość działa lokalnie na otwartym modelu, kod nie trafia do chmury.

## Agenci

Mamy trzech agentów. Eksplorator znajduje pliki i symbole, których dotyczy pytanie. Analityk uruchamia zapytania do grafu (kto zależy od pliku, zasięg zmiany, cykle) i formułuje wnioski z dowodami. Recenzent sprawdza każdy wniosek kodem, nie modelem: czy plik istnieje, czy linia zawiera symbol i czy krawędź jest w grafie. Niepotwierdzony wniosek wraca do Eksploratora, a jeśli dowodów nadal brak, trafia do odpowiedzi jako hipoteza.
