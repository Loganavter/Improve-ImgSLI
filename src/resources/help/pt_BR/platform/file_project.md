## Arquivos e Projetos

Carregue imagens nas listas da sessão, cole a partir da área de transferência e abra ou salve arquivos de projeto portáteis que reúnem layout das sessões, configurações de comparação e cópias das imagens de origem.

### Carregando imagens {#loading-images}

- **Adicionar arquivos** — use os botões de adicionar ao lado (ou {{tr:menu.find_action}}) para escolher um ou mais arquivos.
- **Arrastar e soltar** — soltar na janela coloca os arquivos na lista do lado sob o cursor.
- **Colar** (`Ctrl+V`) — imagem da área de transferência; a sobreposição de direção aparece, um clique em uma seta escolhe o lado, `Esc` cancela.

:::figure{side=block width=280}
![Sobreposição de direção ao colar]({{img:platform.file_project.paste_overlay}})
`Ctrl+V` — sobreposição de direção ao colar.
:::

### Listas {#lists}

- **{{tr:workspace.session_types.image_compare}}** — as listas da esquerda e da direita são independentes; o painel de gerenciamento de lista cobre reordenar, avaliar, renomear, caminho, propriedades e remover — ver [Comparação](help://workspace.image_compare.comparison).
- **{{tr:workspace.session_types.multi_compare}}** — soltura por slot em vez de listas duplas — [{{tr:workspace.session_types.multi_compare}}](help://workspace.multi_compare.overview).

### Projetos {#projects}

- **Abrir / salvar** — `.imgsli` pelo menu Arquivo (`Ctrl+Shift+O` / `Shift+S` / `Ctrl+Shift+S`, ou {{tr:menu.find_action}}): **Salvar** grava o arquivo atual (ou abre **Salvar como** se ainda não foi salvo); **Salvar como** usa o título da aba se ela foi renomeada, senão {{tr:menu.project_untitled}}. **Salvar** também renomeia o arquivo quando a aba mudou. Ao abrir um projeto, a aba ativa recebe o nome do arquivo. Restaura as sessões do workspace, as configurações de comparação (split, diff, lupa e recursos relacionados) e cópias incorporadas das imagens.
- **Pacote portátil** — o arquivo é um ZIP: JSON das sessões mais uma pasta `media/` com cópias byte a byte dos originais (sem reencodar buffers de pixel).
- **Fontes ausentes ao salvar** — se um caminho da lista não existir mais, o projeto ainda é salvo; essa imagem é omitida e um aviso a lista.
- **Preferências do app** — tema, idioma e atalhos permanecem nas configurações do aplicativo; não fazem parte do arquivo de projeto.
