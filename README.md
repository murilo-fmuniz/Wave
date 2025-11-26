# Wave — Mouse Virtual por Detecção de Cor (Webcam)

Aplicação Python simples para controlar o cursor do Windows usando detecção de cores pela webcam.

## Instalação

Instale dependências via pip (recomendado usar um ambiente virtual):

```powershell
py -3.13 -m pip install -r requirements.txt
```
## Como executar

```powershell
py -3.13 wave.py
```

Ao executar:
1. A janela `Detector de Cor` abre mostrando a câmera.
2. Clique sobre o objeto (com o cursor) para capturar sua cor de referência.
3. O sistema rastreará o objeto; se ele sair da cena, o algoritmo fará buscas ao redor da última posição e abrirá tolerância para cores semelhantes.


## Teclas / Controles

- `a` : clique esquerdo (curto). Se a biblioteca `keyboard` estiver instalada, segurando `a` pressiona/segura o botão até soltar.
- `l` : clique direito (curto). Suporte a press-and-hold via `keyboard` quando disponível.
- `0` : alterna o modo mouse virtual (oculta/mostra a janela). Quando ativo, o cursor segue o objeto detectado.
- `R` : reset — limpa cor capturada, posição e estados de rastreio.
- `Esc` : encerra o programa.

## Dicas de uso

- Use cores vibrantes e contrastantes com o fundo.
- Mantenha distância adequada (teste entre 20–50 cm).
- Iluminação consistente melhora o reconhecimento.
- Ajuste foco da câmera se necessário.

## Arquivos principais

- `wave.py` — script principal (detector + modo mouse virtual)
- `requirements.txt` — dependências

## Requisitos

- Python 3.13+
- Webcam funcional
- Windows 10/11 (recomenda-se)

## Problemas comuns e soluções

- Se o programa não captura teclas quando a janela está minimizada/out-of-focus, instale `keyboard` e rode o script como Administrador para permitir hotkeys globais:

```powershell
py -3.13 -m pip install keyboard
# Em seguida: execute o PowerShell como Administrador e rode
py -3.13 wave.py
```

- Se o Windows bloquear ações de automação (SmartScreen / Defender):
	- Execute o programa a partir de uma pasta confiável (ex.: `C:\Users\SeuUsuario\Documents`).
	- Adicione exclusão no Defender para a pasta do projeto.
	- Considere empacotar/sinalizar para distribuição (opcional).

## Ajustes rápidos

- Para calibrar sensibilidade, edite `area_threshold` dentro do `wave.py`.
- Se o cursor pular ao restaurar a janela, aumentar `KEY_DEBOUNCE` no topo do arquivo pode reduzir duplicações de eventos.

---

Se quiser, eu posso: (a) tornar `a`/`l` também globais, (b) adicionar overlay textual quando ações globais acontecem, ou (c) criar um pequeno script de instalação. Diga qual prefere.
