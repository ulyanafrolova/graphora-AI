# Graphora — scenariusz prezentacji

## Problem

Agenci AI piszą dziś coraz więcej kodu, i to szybciej, niż ludzie są w stanie go zrozumieć. W efekcie programiści spędzają coraz więcej czasu na przeglądaniu kodu, którego sami nie napisali. Najważniejsze pytanie brzmi wtedy: co się zepsuje, jeśli zmienię ten fragment? Dzisiejsi asystenci odpowiadają na nie tekstem, który bywa błędny i za każdym razem trzeba go sprawdzać od nowa.

## Jak to rozwiązujemy i dlaczego potrzebne jest AI

Łączymy dwie rzeczy: dokładną mapę zależności w kodzie i agentów AI, którzy z tej mapy korzystają. Sama mapa jest precyzyjna, ale w dużym projekcie ma tysiące plików i człowiek się w niej gubi. Nie odpowie też na pytanie zadane zwykłym językiem ani nie wyjaśni, dlaczego dana zmiana jest ryzykowna. To robi AI: rozumie pytanie, wybiera właściwe fragmenty mapy i tłumaczy wynik po ludzku. Samo AI potrafi jednak zmyślać, dlatego każde jego twierdzenie sprawdzamy na mapie, a to, czego nie da się potwierdzić, oznaczamy jako hipotezę.

## Co robi nasz system

Użytkownik podaje link do repozytorium na GitHubie. Graphora analizuje kod i rysuje interaktywną mapę: które pliki od siebie zależą, gdzie są cykle i które miejsca są najbardziej ryzykowne. Potem można zadać pytanie, na przykład „Co się zepsuje, jeśli zmienię AuthService?”, i dostać odpowiedź ze wskazaniem konkretnych plików i linii, podświetlonych na mapie. Z tej samej mapy mogą korzystać zewnętrzni agenci, tacy jak Claude Code czy Cursor, żeby oni też pracowali na faktach. Wszystko może działać lokalnie, bez wysyłania kodu do chmury.

## Agenci

W systemie pracuje trzech agentów, którzy przekazują sobie zadanie. Eksplorator szuka w repozytorium plików i fragmentów kodu związanych z pytaniem. Analityk odpytuje mapę zależności i na tej podstawie formułuje wnioski razem z dowodami. Recenzent sprawdza każdy wniosek: czy plik istnieje, czy wskazana linia naprawdę zawiera ten kod i czy zależność jest na mapie. Jeśli dowodów brakuje, odsyła zadanie do Eksploratora, a gdy nadal się nie da, oznacza wniosek jako hipotezę. Dzięki temu użytkownik dostaje tylko sprawdzone odpowiedzi i widzi, jak agenci doszli do wyniku.
