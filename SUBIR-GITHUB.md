# Subir este repositório no GitHub

O Git já está inicializado e o commit inicial foi feito. Siga um dos caminhos abaixo.

---

## Opção 1 – Criar o repositório no site e dar push

### 1. Criar o repositório no GitHub

1. Acesse [github.com/new](https://github.com/new).
2. **Repository name:** por exemplo `Libnest2D` (ou `nest-local`).
3. Escolha **Public** ou **Private**.
4. **Não** marque “Add a README”, “Add .gitignore” nem “Choose a license” (o projeto já tem conteúdo).
5. Clique em **Create repository**.

### 2. Conectar e enviar o código

No terminal, na pasta do projeto (`/Users/luvizon/Documents/GitHub/Libnest2D`), rode (troque `SEU_USUARIO` e `Libnest2D` pelo seu usuário/org e nome do repositório):

```bash
cd /Users/luvizon/Documents/GitHub/Libnest2D

git remote add origin https://github.com/SEU_USUARIO/Libnest2D.git
git branch -M main
git push -u origin main
```

Se o GitHub pedir autenticação, use um **Personal Access Token** (Settings → Developer settings → Personal access tokens) como senha, ou configure SSH e use a URL com SSH:

```bash
git remote add origin git@github.com:SEU_USUARIO/Libnest2D.git
git push -u origin main
```

---

## Opção 2 – Usar GitHub CLI (se instalar depois)

```bash
brew install gh
gh auth login
cd /Users/luvizon/Documents/GitHub/Libnest2D
gh repo create Libnest2D --private --source=. --remote=origin --push
```

(Altere `Libnest2D` e `--private` conforme quiser.)

---

Depois do primeiro `git push`, o repositório estará no GitHub.
