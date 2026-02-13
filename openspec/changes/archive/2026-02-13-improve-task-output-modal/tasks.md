## 1. Dependencies

- [x] 1.1 Install `marked` and `@types/marked` as frontend dependencies
- [x] 1.2 Install `dompurify` and `@types/dompurify` as frontend dependencies
- [x] 1.3 Install `@tailwindcss/typography` as a frontend dev dependency and add it to the Tailwind config plugins

## 2. Modal Width

- [x] 2.1 Update `TaskOutputModal.vue` to replace `w-[36rem]` with `w-[90vw] max-w-5xl` for responsive width

## 3. Markdown Rendering

- [x] 3.1 Add markdown rendering logic to `TaskOutputModal.vue`: import `marked` and `DOMPurify`, create a computed property that parses the output string and sanitizes the HTML
- [x] 3.2 Replace the `<pre>` output block with a `<div>` using `v-html` and Tailwind `prose` class to display the rendered markdown
- [x] 3.3 Ensure the "No output available" fallback still displays when output is null or empty

## 4. Tests

- [x] 4.1 Update existing `TaskOutputModal` tests to account for the new rendered markdown output (wider modal, `v-html` content)
- [x] 4.2 Add test: markdown headings, lists, and horizontal rules render as HTML elements
- [x] 4.3 Add test: plain text output renders without artifacts
- [x] 4.4 Add test: dangerous HTML tags are sanitized from output

## 5. Version Bump

- [x] 5.1 Bump `VERSION` file (minor version increment for new frontend capability)
