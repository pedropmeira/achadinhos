# Achadinhos — Mercado Livre → TikTok

Tudo roda de graça na nuvem do GitHub. Seu PC não precisa ficar ligado.
Depois de configurado, você opera **100% pelo celular**.

## Como funciona

1. **A cada 3h** o radar busca os mais vendidos do ML e calcula o **retorno em R$** (preço × comissão).
2. No **app (painel)** você vê as sugestões ordenadas por retorno.
3. Para cada uma que quiser, toque em **Gerar link**: o link do produto já vai copiado. Gere o link de afiliado, volte, toque em **Colar** e depois em **Aprovar e criar vídeo**.
4. Em ~2 min o vídeo aparece em **Para postar**.
5. Toque em **Postar no TikTok**: a legenda é copiada e o vídeo abre direto no compartilhar do celular. Escolha o TikTok, coloque um **som em alta**, cole a legenda e marque **conteúdo comercial**.
6. Toque em **Já postei**.
7. A oferta entra na **vitrine** (o link da bio) com o mesmo número do vídeo. A pessoa digita o nº e cai no seu link.

O radar também confere a vitrine a cada busca. Tira sozinho o que saiu do ar, subiu de preço ou passou de 15 dias.

---

## Configuração (uma vez, ~30 min, melhor no computador)

### 1. Repositório no GitHub
1. Crie uma conta em github.com (se ainda não tiver).
2. **New repository** → nome `achadinhos` → **Public**. Precisa ser público para Pages e Actions serem grátis; nada sensível fica exposto.
3. Em **Add file → Upload files**, arraste **todo o conteúdo** desta pasta, incluindo a pasta `.github`, e confirme.

### 2. Site (vitrine + app)
**Settings → Pages** → *Deploy from a branch* → `main` / pasta `/docs` → Save.
Em ~1 min ficam no ar:
- Vitrine (link da bio): `https://SEU-USUARIO.github.io/achadinhos/`
- App: `https://SEU-USUARIO.github.io/achadinhos/painel.html`

### 3. Token do GitHub
**Foto do perfil → Settings → Developer settings → Fine-grained tokens → Generate new token**
- Repository access: **Only select repositories** → `achadinhos`
- Permissions: **Contents: Read and write** e **Secrets: Read and write**
- Expiração: 1 ano. Guarde o token, ele vai em dois lugares.

### 4. App no Mercado Livre (API oficial, grátis)
1. Entre em developers.mercadolivre.com.br com sua conta → **Minhas aplicações → Criar**.
2. Redirect URI: `https://www.google.com.br`
3. Anote o **App ID** e a **Secret Key**.

### 5. Segredos do repositório
**Settings → Secrets and variables → Actions → New repository secret**. Crie três:

| Nome | Valor |
|---|---|
| `ML_CLIENT_ID` | App ID do ML |
| `ML_CLIENT_SECRET` | Secret Key do ML |
| `GH_PAT` | o token do passo 3 |

### 6. Autorizar o Mercado Livre
1. Abra no navegador, trocando `APP_ID` pelo seu:
   `https://auth.mercadolivre.com.br/authorization?response_type=code&client_id=APP_ID&redirect_uri=https://www.google.com.br`
2. Autorize. Você cai no Google com `?code=...` na barra. **Copie a URL inteira.**
3. No GitHub: **Actions → Autorizar Mercado Livre → Run workflow**, cole a URL e rode. O code vale poucos minutos.

O token se renova sozinho daí em diante. Se um dia der erro de autorização, repita só este passo.

### 7. Suas comissões
Edite o `config.json` (no GitHub, ícone de lápis). Coloque a **comissão real de cada categoria** que aparece no seu painel de afiliados; os valores atuais são ilustrativos. Também dá para trocar o nome do perfil, os filtros e as cores do vídeo.

### 8. Primeira busca
**Actions → Achadinhos → Run workflow**. Em ~3 min as sugestões aparecem no app.

---

## No celular

1. Abra `https://SEU-USUARIO.github.io/achadinhos/painel.html`.
2. Nas configurações, cole o **token** e toque em **Salvar e testar**.
3. **Adicione à tela inicial**: no iPhone, Safari → Compartilhar → *Adicionar à Tela de Início*; no Android, Chrome → ⋮ → *Adicionar à tela inicial*. Fica como um app.
4. Opcional: em configurações, ajuste o endereço do **gerador de links** se o padrão não abrir a página certa do seu painel de afiliados.

## No TikTok
- **Link da bio**: coloque a vitrine. Em conta pessoal o link só libera com 1.000 seguidores; em **conta empresa** não tem mínimo, mas algumas músicas ficam indisponíveis.
- Sempre ative **conteúdo comercial** nos posts de afiliado.
- Varie: alterne os vídeos automáticos com vídeos seus (unboxing, teste, opinião). Perfil que só posta vídeo gerado tende a perder alcance.

## Regras para não perder a conta de afiliado
- Nunca compre pelo próprio link.
- Nada de anúncio pago em buscador com o link.
- Gere link só de **página de produto**.

## Ajustes úteis no `config.json`

| Campo | O que faz |
|---|---|
| `min_retorno_reais` | Só sugere se a comissão estimada for ≥ esse valor |
| `min_desconto_pct` | Ex.: `15` = só itens com 15% OFF ou mais |
| `max_sugestoes_por_varredura` | Quantas sugestões novas a cada busca |
| `oferta_valida_dias` | Por quantos dias a oferta fica na vitrine |
| `hashtags` | Hashtags da legenda |
| `video` | Cores e duração do vídeo |

IDs de categoria: `https://api.mercadolibre.com/sites/MLB/categories`
