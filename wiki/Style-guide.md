## Python Style Guide

This Python style guide outlines best practices for code consistency, readability, and maintainability.

### 1. PEP 8 Compliance
- **Line Length:** Limit lines to 79 characters.
- **Indentation:** Use 4 spaces per indentation level, never tabs.
- **Whitespace:** Avoid unnecessary whitespace inside parentheses, brackets, or braces.

### 2. Naming Conventions
- **Variables:** Use snake_case (e.g., `user_name`).
- **Functions:** Use snake_case (e.g., `calculate_sum`).
- **Classes:** Use PascalCase (e.g., `DataProcessor`).
- **Constants:** Use uppercase with underscores (e.g., `MAX_LIMIT`).

### 3. Imports
Group imports in the following order, separated by blank lines:
1. Standard library imports
2. Third-party library imports
3. Local application imports

Use absolute imports whenever possible.

### 4. Comments and Docstrings
- Include docstrings for all modules, classes, methods, and functions.
- Use triple-double quotes for docstrings (`"""This is a docstring."""`).
- Follow the Google-style format for detailed descriptions.

### 5. Code Structure
- Limit function length to 20 lines or less when practical.
- Limit class length to fewer than 200 lines.
- Limit files to under 250 lines.

### 6. Error Handling
- Use specific exceptions (`ValueError`, `KeyError`) rather than generic ones (`Exception`).
- Clearly document exceptions in function docstrings.

### 7. Readability and Simplicity
- Write clear, self-explanatory code.
- Prefer list comprehensions and generator expressions where appropriate.
- Avoid overly clever or complex expressions.

### 8. Testing
- Include unit tests for all modules and key functions.
- Place tests in a `tests/` directory alongside the module being tested.
- Use descriptive test names: `test_module.py`, `test_functionality()`.
- Use `pytest` for running tests.

### 9. Type Hints
- Use type hints for all function parameters and return values.
- Use `Optional` for nullable parameters.

### 10. Documentation
- **ALL user-facing and architectural documentation goes in the wiki repository** (`airunner.wiki`)
- Component-level `README.md` files within `src/` are acceptable for internal developer docs
- Update the wiki to reflect changes in the codebase

### 11. Version Control
- Write clear and descriptive commit messages.
- Follow the Git flow model (feature branches, merge requests, main/develop branches).
