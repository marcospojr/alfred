# RESUMO PARA A IA: conectar uma API
Ferramenta: conector_criar(nome, descricao, base_url, auth, endpoints, local). Depois use conector_leitura (endpoints V) ou conector_acao (A/R, sempre confirma). Parâmetros são um OBJETO: {"cep":"88010400"}.
base_url: https obrigatório. auth: {"tipo":"nenhum"} | {"tipo":"bearer","segredo":"nome-no-cofre"} | {"tipo":"header","campo":"X-API-Key","segredo":"..."} | {"tipo":"query","campo":"apikey","segredo":"..."}.
A chave NUNCA passa por você: diga à pessoa para rodar `python -m alfred chave <segredo>`.
endpoints: [{"nome":"buscar-cep","metodo":"GET","caminho":"/ws/{cep}/json/","descricao":"...","risco":"V"}]. {x} no caminho vem dos parâmetros; o resto vai na query (GET) ou no corpo JSON. Sem risco: GET=V, outros=A. Use R para dinheiro, envio, exclusão.
Exemplo: {"nome":"viacep","base_url":"https://viacep.com.br","auth":{"tipo":"nenhum"},"endpoints":[{"nome":"buscar-cep","metodo":"GET","caminho":"/ws/{cep}/json/"}]}
Depois: habilitar_grupo('integracoes'); conector_leitura(conector="viacep", endpoint="buscar-cep", parametros={"cep":"88010400"}). Leia a resposta antes de afirmar qualquer coisa.
<!--completo-->
# Como conectar APIs ao Alfred (conectores)

Um conector é um arquivo `conectores/<nome>.json` que descreve uma API HTTP. O Alfred passa a conversar com ela por duas ferramentas:
- `conector_leitura(conector, endpoint, parametros)` para endpoints de risco **V** (só leem). Roda sem confirmação.
- `conector_acao(...)` para endpoints **A** ou **R** (mudam algo, enviam, cobram, apagam). **Sempre confirma**, mostrando método, caminho e parâmetros.

Para criar: `conector_criar` (a pessoa aprova), `conector_listar` para ver o que existe.

## Formato
```json
{
  "nome": "minha-api",
  "descricao": "para que serve",
  "base_url": "https://api.exemplo.com",
  "auth": { "tipo": "bearer", "segredo": "minha-api-chave" },
  "endpoints": [
    { "nome": "listar-clientes", "metodo": "GET",  "caminho": "/v1/clientes",     "descricao": "lista" },
    { "nome": "criar-cliente",   "metodo": "POST", "caminho": "/v1/clientes",     "risco": "A", "descricao": "parametros: nome, email" },
    { "nome": "ver-pedido",      "metodo": "GET",  "caminho": "/v1/pedidos/{id}", "descricao": "pedido por id" },
    { "nome": "cobrar",          "metodo": "POST", "caminho": "/v1/cobrancas",    "risco": "R", "descricao": "valor, cliente_id" }
  ]
}
```
- `auth.tipo`: `nenhum`, `bearer` (Authorization: Bearer), `header` (precisa de `campo`, ex.: `X-API-Key`) ou `query` (precisa de `campo`, ex.: `apikey`).
- `auth.segredo`: **nome** da entrada no cofre do sistema. **Você nunca vê nem escreve a chave.** A pessoa guarda com `python -m alfred chave minha-api-chave` (a chave não aparece na tela).
- `{id}` no caminho é preenchido pelos `parametros`; o que sobrar vai na query (GET) ou no corpo JSON (POST/PUT/PATCH/DELETE).
- `risco`: omitido, GET vira V e os outros viram A. Marque **R** para dinheiro, envio para terceiros, exclusão.
- `base_url` precisa ser `https`. Só para APIs na própria máquina use `"local": true` com `http://localhost...`.

## Receita (da documentação da API ao conector)
1. Peça à pessoa o link da documentação (ou o OpenAPI/Swagger). Leia com `ler_pagina`.
2. Escolha só os endpoints que a pessoa precisa (não importe a API inteira).
3. Classifique o risco de cada um com honestidade (na dúvida, suba o risco).
4. Crie o conector. Se houver chave, diga à pessoa o comando exato `python -m alfred chave <segredo>` e espere ela dizer que guardou.
5. Teste um endpoint de leitura e mostre o resultado antes de usar em automações.
6. Use em automações com `{"ferramenta": "conector_leitura", "args": {...}}`. Para `conector_acao` dentro de automação, a ferramenta precisa estar em `permite`.

## Exemplos prontos em `presets/conectores/`
`viacep.json` (endereço por CEP, sem chave) e `open-meteo.json` (previsão do tempo, sem chave) funcionam de verdade; `exemplo-api-com-chave.json` é um modelo.
Copie o arquivo para a pasta `conectores/` (ou peça: "conecte a API ViaCEP").

## Webhooks de saída e n8n/Zapier
Para avisar um fluxo seu (n8n, Make, Zapier), crie um conector com `base_url` do servidor deles e um endpoint POST de risco A ou R no caminho do webhook.
