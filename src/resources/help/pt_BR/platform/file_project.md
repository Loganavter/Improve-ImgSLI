---
description: Como as imagens entram na sessão e o que o projeto reúne.
icon: folder_open.svg
---
## Arquivos e Projetos

Carregue imagens nas listas da sessão, cole a partir da área de transferência e abra ou salve um arquivo de projeto que reúne o leiaute da sessão, as configurações de comparação e cópias das imagens de origem.

### Carregando imagens {#loading-images}

- **Adicionar Imagem(ns) 1** / **Adicionar Imagem(ns) 2** — os botões de adicionar ao lado das listas da esquerda e da direita abrem um seletor de arquivos; escolha uma ou várias imagens para aquele lado.
- **Adicionar imagens** — em **Comparação múltipla**, um único botão de adicionar carrega imagens na grade.
- **Arrastar e soltar** — solte arquivos na janela; eles entram na lista do lado sob o cursor.
- **Colar imagem da área de transferência** (`Ctrl+V`) — a imagem vai para a sessão ativa. Surge uma sobreposição de direção: clique em uma seta para escolher o lado, ou pressione `Esc` para cancelar.

:::figure{side=block width=280}
![Sobreposição de direção ao colar](../../assets/platform/paste_overlay.jpg)
Sobreposição de direção após `Ctrl+V`: clique em uma seta para enviar a imagem colada à lista da esquerda ou da direita.
:::

### Listas {#lists}

- Em **Comparar imagens**, as listas da esquerda e da direita são independentes. O painel gerenciador de lista permite reordenar, avaliar, renomear, ver o caminho, abrir as propriedades e remover imagens — veja [Comparação](help://workspace.image_compare.comparison).
- Em **Comparação múltipla**, as imagens vão para slots individuais em vez de duas listas — veja [Visão Geral do Multi Compare](help://workspace.multi_compare.overview).

Cada sessão tem sua própria aba; veja [Abas](help://platform.tabs).

### Projetos {#projects}

Um arquivo de projeto (`.imgsli`) guarda um espaço de trabalho inteiro em um único arquivo portátil: as sessões abertas, suas configurações de comparação e cópias das imagens de origem.

- **Abrir projeto** — no menu **Arquivo**, com `Ctrl+Shift+O`, ou em **Localizar ação**. A aba ativa recebe o nome do arquivo, e o projeto restaura as sessões, as configurações de comparação (divisor, diferenças, lupa e recursos relacionados) e as cópias incorporadas das imagens.
- **Salvar projeto** — `Shift+S` grava o arquivo atual. Quando ainda não existe arquivo, abre **Salvar projeto como…**. Ao salvar, o nome do arquivo também é atualizado se a aba foi renomeada.
- **Salvar projeto como…** — `Ctrl+Shift+S` sugere o nome da aba renomeada; caso contrário, **Sem título**.
- **O que o arquivo contém** — um arquivo ZIP: `project.json` com as sessões e uma pasta `media/` com uma cópia incorporada de cada imagem.
- **Se um original estiver ausente** — quando um caminho da lista não existe mais, o projeto ainda é salvo; essa imagem é omitida e um aviso informa seu nome.
- **O que não é salvo** — o tema, o idioma e os atalhos ficam nas configurações do aplicativo; não fazem parte do arquivo de projeto.

### Duplo clique em um projeto no Windows {#windows-file-association}

No Windows, o instalador associa `.imgsli` ao BlinkTable, então um duplo clique abre o projeto e o arquivo exibe o ícone de documento do aplicativo. As compilações empacotadas também registram a associação ao iniciar.

Se as Propriedades ainda mostrarem "Escolher um aplicativo", selecione o BlinkTable uma vez, ou execute o aplicativo com `--register-file-types` para registrar a associação novamente.
