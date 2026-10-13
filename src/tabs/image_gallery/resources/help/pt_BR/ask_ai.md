---
description: Receber comentários da IA sobre uma foto, seleção ou série.
icon: ai.svg
---
## Perguntar à IA

Perguntar à IA responde a perguntas sobre um único cartão, a seleção atual ou uma série inteira. As respostas são consultivas e sempre carregam um selo que as marca como fornecidas por IA.

### Perguntar sobre uma seleção {#ask-selection}

- **IA…** — abre **Perguntar à IA** para esse cartão ou a seleção atual.
- **O que importa aqui?** — a pergunta padrão; pede ao modelo que resuma as imagens que recebe.
- **Leitura de IA, não verificada** — o selo no texto produzido pela IA; ele marca a resposta como não verificada.

### Perguntar sobre uma série {#ask-series}

O menu do cabeçalho da série pergunta de uma vez sobre cada membro da série. As leituras de nitidez e ruído vêm de [Métricas de qualidade](help://workspace.image_gallery.quality) e são mostradas sem uma requisição ao modelo de IA.

### Configuração e limites {#setup}

- **Galeria — IA** — a seção de configurações por trás de Perguntar à IA; perguntar exige **Ativar análise de imagem por IA**, uma chave de API e um modelo. Configure em [Configurações](help://platform.settings#image-gallery-ai). Sem os três, o aplicativo mostra **Configure a chave de API de IA nas Configurações primeiro.**
- Enquanto o modelo trabalha, o painel mostra **Pensando…**; uma requisição malsucedida informa **A IA não conseguiu responder.**
- As respostas nunca alteram o ranking, a seleção ou qualquer estado armazenado.
- A mesma pergunta reutiliza a resposta em cache; um novo modelo ou novas imagens perguntam ao modelo novamente.
