# Development Prompts

## Dev Environment Initialization
```
Create the starting structure for this project.

\\- Add backend/
\\- Add frontend/
\\- Add README.md for the goal and setup.
\\- Add AGENTS.md for project rules.
```

```
Verify the development environment.

Do not create application code.

Confirm:
\\- which Python interpreter belongs to this project;
\\- that FastAPI can be imported;
\\- the Node.js and npm versions;
\\- that the frontend package environment is ready;
\\- every file or directory created.

Report any check that did not pass.
```

```
Read AGENTS.md and README.md.

Do not write any backend function, API route, test, or frontend application code.

Prepare the backend development environment:
\\- create backend/.venv using the compatible Python that just passed verification;
\\- create backend/requirements.txt containing fastapi[standard] and pytest;
\\- install only those declared dependencies into backend/.venv;
\\- verify that the interpreter used for the checks belongs to backend/.venv;
\\- verify that fastapi and pytest import successfully.

Do not install Python packages globally. Ask before any machine-level change.
Report every file or directory created, every command run, and the evidence from each check.
```


```
Read AGENTS.md and README.md.

Initialize a minimal JavaScript Vue project inside the existing empty frontend/ folder.
\\- use the current official create-vue workflow;
\\- do not create a second nested frontend folder;
\\- do not install Vue or Vue CLI globally;
\\- omit Router, Pinia, TypeScript, JSX, unit-test, and end-to-end-test options;
\\- include ESLint for code-quality checks;
\\- install the declared frontend dependencies;
\\- run the frontend lint and production-build checks.

The generated Vue starter screen is allowed, but do not build an application interface yet.
Do not change backend files.
Report every file or directory created, every command run, and the evidence from each check.
```


```
Read AGENTS.md and README.md.

Before writing application code, verify:
\\- the backend Python interpreter belongs to backend/.venv;
\\- fastapi and pytest import through that interpreter;
\\- Node.js and npm satisfy the Vue project requirement;
\\- frontend/package.json declares Vue;
\\- the existing frontend lint and production build pass.

Do not install, upgrade, or change dependencies.
Report any failed or partial check and stop if the project is not ready.
```



## First Iteration Planning
```
Read AGENTS.md and README.md. Plan the smallest implementation of the expeida replica.
The backend owns logic and FastAPI paths.\
The Vue frontend owns inputs, controls, requests, and presentation.\
The layers communicate through JSON.
Do not edit files yet. Identify:\
\- the files you expect to create or modify;\
\- the order of the work;\
\- the checks that will prove each layer works;\
\- any decision that requires my approval.
```