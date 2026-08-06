---
name: frontend-design
description: Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, or applications. Generates creative, polished code that avoids generic AI aesthetics.
license: Complete terms in LICENSE.txt
---

This skill guides creation of distinctive, production-grade frontend interfaces that avoid generic "AI slop" aesthetics. Implement real working code with exceptional attention to aesthetic details and creative choices.

The user provides frontend requirements: a component, page, application, or interface to build. They may include context about the purpose, audience, or technical constraints.

## Project Conventions Priority

Before applying creative guidelines, check for existing project constraints:
- Design system files (ui-conventions, design-tokens, theme config)
- CLAUDE.md frontend guidelines
- Existing component library (shadcn/ui, MUI, etc.)
- Brand guidelines or style guides

**If project conventions exist:** Follow them. Use this skill's principles for quality and attention to detail, but respect established patterns, colors, and typography.

**If no conventions exist:** Apply full creative freedom below.

## Design Thinking

Before coding, understand the context and commit to a clear aesthetic direction:
- **Purpose**: What problem does this interface solve? Who uses it?
- **Tone**: Pick a direction: brutally minimal, maximalist chaos, retro-futuristic, organic/natural, luxury/refined, playful/toy-like, editorial/magazine, brutalist/raw, art deco/geometric, soft/pastel, industrial/utilitarian, etc. Use these for inspiration but design one that is true to the aesthetic direction. If project has established tone — align with it.
- **Constraints**: Technical requirements (framework, performance, accessibility), project conventions.
- **Differentiation**: What makes this memorable? What's the one thing someone will notice?

**CRITICAL**: Choose a clear conceptual direction and execute it with precision. Bold maximalism and refined minimalism both work — the key is intentionality, not intensity.

Then implement working code (HTML/CSS/JS, React, Vue, etc.) that is:
- Production-grade and functional
- Visually striking and memorable
- Cohesive with a clear aesthetic point-of-view
- Meticulously refined in every detail

## Frontend Aesthetics Guidelines

Focus on:
- **Typography**: If project defines fonts — use them consistently. Otherwise, choose fonts that are beautiful and appropriate for the context. For unrestricted projects, prefer distinctive choices over generic defaults. Pair a display font with a refined body font when appropriate.
- **Color & Theme**: Follow project palette if defined. Otherwise, commit to a cohesive aesthetic. Use CSS variables for consistency. Dominant colors with sharp accents outperform timid, evenly-distributed palettes.
- **Motion**: Use animations for effects and micro-interactions. Prioritize CSS-only solutions for HTML. Use Motion library for React when available. Focus on high-impact moments: one well-orchestrated page load with staggered reveals (animation-delay) creates more delight than scattered micro-interactions. Use scroll-triggering and hover states that surprise.
- **Spatial Composition**: Unexpected layouts. Asymmetry. Overlap. Diagonal flow. Grid-breaking elements. Generous negative space OR controlled density. Adapt to project's layout conventions if they exist.
- **Backgrounds & Visual Details**: Create atmosphere and depth rather than defaulting to solid colors. Add contextual effects and textures that match the overall aesthetic. Apply creative forms like gradient meshes, noise textures, geometric patterns, layered transparencies, dramatic shadows, decorative borders, custom cursors, and grain overlays.

When no project conventions exist, avoid defaulting to generic patterns: overused font families without reason, cliched color schemes (particularly purple gradients on white backgrounds), predictable layouts, and cookie-cutter design that lacks context-specific character.

Interpret creatively and make choices that feel genuinely designed for the context. When you have creative freedom, vary between light and dark themes, different fonts, different aesthetics — don't converge on the same choices across generations.

**IMPORTANT**: Match implementation complexity to the aesthetic vision. Maximalist designs need elaborate code with extensive animations and effects. Minimalist or refined designs need restraint, precision, and careful attention to spacing, typography, and subtle details. Elegance comes from executing the vision well.

Remember: Claude is capable of extraordinary creative work. Don't hold back, show what can truly be created when thinking outside the box and committing fully to a distinctive vision.

## Adaptation Mode

This skill operates in two modes:

**Constrained mode** (project has design system):
- Follow existing color palette, typography, spacing, component library
- Apply quality principles: attention to detail, polished animations, spatial composition
- Enhance within boundaries, don't override
- Focus on refinement and consistency

**Creative mode** (greenfield project or no conventions):
- Full aesthetic freedom
- Bold, distinctive choices
- Avoid generic patterns
- Create memorable, unique designs
