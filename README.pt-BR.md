# Xcode Skills

Dois plugins de orientações do Xcode, mantidos por **Henrique Velloso**:

- `xcode-apple-skills`: fonte Xcode release.
- `xcode-apple-skills-preview`: fonte beta/RC, com skills terminadas em `-preview`.

Os dois usam a mesma versão de pacote. A versão e o build exatos do Xcode de
cada canal estão no [catálogo atualizado](README.md#included-sources-and-skills)
e na proveniência dos pacotes. O projeto não é oficial da Apple, OpenAI ou
Anthropic. As orientações respeitam a arquitetura e as regras de cada projeto.

## Codex

```sh
codex plugin marketplace add henriquevelloso/xcode-skills
codex plugin add xcode-apple-skills@xcode-skills
codex plugin add xcode-apple-skills-preview@xcode-skills
```

Pode instalar um ou ambos. Abra um novo chat e confira a descoberta das skills.
Para atualizar o catálogo: `codex plugin marketplace upgrade xcode-skills`;
depois confira a atualização do plugin pelo mecanismo suportado do cliente.

## Claude Code

```text
/plugin marketplace add henriquevelloso/xcode-skills
/plugin install xcode-apple-skills@xcode-skills
/plugin install xcode-apple-skills-preview@xcode-skills
```

Escolha a edição desejada pelo nome, por exemplo:
`/xcode-apple-skills-preview:swiftui-specialist-preview`.
Não duplique a instalação com links manuais das mesmas skills.

## Atualizações automáticas

A rotina local verifica os lançamentos oficiais e os Xcodes instalados todos
os dias às **09h, no fuso America/Sao_Paulo**. Quando falta uma versão, informa
qual versão/build baixar e o link oficial. Não baixa nem instala o Xcode.
Após exportação, revisão automatizada e testes, atualizações geradas pela rotina
do proprietário entram por PR com auto-merge e publicação automática.

O Mac e o Codex precisam estar disponíveis para exportar/adaptar. Uma checagem
sem novidade não gera release. Se mudar apenas o preview, a revisão compartilhada
do pacote avança e as notas deixam claro que o canal release não mudou.
Falhas preservam o último conteúdo válido e não são tratadas como aprovação
manual obrigatória por versão.

Cada [release](https://github.com/henriquevelloso/xcode-skills/releases) contém
os dois ZIPs, checksums, proveniência e notas. É possível fixar uma tag para uso
reproduzível. Outros agentes podem consumir as pastas de skills, mas precisam
ter as ferramentas exigidas; ler a documentação na nuvem não fornece Xcode.

## Procedência e licença

Henrique Velloso é autor/mantenedor do projeto e das contribuições próprias,
não autor das orientações upstream da Apple. A licença MIT não relicencia
material de terceiros. Não foi fornecida licença separada com a exportação
usada na primeira versão; a publicação não comprova direitos de redistribuição.
Leia os [avisos de terceiros](THIRD_PARTY_NOTICES.md) antes de redistribuir.
A documentação completa e os comandos de manutenção estão no [guia em inglês](README.md).
