# LearnFlow AI Web UI

A React-based web interface for LearnFlow AI educational content generation system. Built with TypeScript, Vite, and modern UI components.

## Overview

The LearnFlow AI Web UI provides an intuitive interface for:
- Submitting educational questions and tasks
- Uploading handwritten notes for OCR processing
- Real-time workflow monitoring and progress tracking
- Interactive review and editing of generated materials
- Export functionality for study materials (PDF/Markdown)

## Features

### Core Functionality
- **Question Input**: Text area for educational questions from any subject area
- **Note Upload**: Drag-and-drop interface for handwritten note images
- **Workflow Visualization**: Real-time progress tracking through LangGraph nodes
- **Material Preview**: Live preview of generated educational content
- **Interactive Editing**: In-browser editing with syntax highlighting
- **Export Options**: PDF and Markdown export with customizable templates
- **Deep Linking**: Direct URL navigation to specific threads, sessions, and files
- **Browser Navigation**: Full support for back/forward buttons and bookmarks

### UI Components
- **Material Viewer**: Rich markdown rendering with LaTeX support
- **Progress Indicator**: Visual workflow progress with node status
- **File Manager**: Organized view of uploaded images and generated materials
- **Settings Panel**: Configuration for HITL modes and export preferences

## Architecture

### Technology Stack
- **Frontend**: React 18 + TypeScript
- **Build Tool**: Vite for fast development and optimized builds
- **Styling**: CSS Modules + Modern CSS features
- **State Management**: React Context + Hooks
- **Routing**: React Router with deep linking support
- **HTTP Client**: Fetch API with custom hooks
- **File Handling**: HTML5 File API for uploads

### Project Structure
```
web-ui/
├── src/
│   ├── components/           # Reusable UI components
│   │   ├── AccordionSidebar/ # Hierarchical navigation with URL-driven state
│   │   ├── RouteGuard/       # Route validation and protection
│   │   ├── QuestionInput/    # Educational question input form
│   │   ├── ImageUpload/      # Drag-and-drop file upload
│   │   ├── WorkflowViewer/   # Workflow progress visualization
│   │   ├── MaterialEditor/   # Interactive content editor
│   │   └── ExportDialog/     # Export configuration modal
│   ├── hooks/                # Custom React hooks
│   │   ├── useNavigation.ts  # Navigation utilities and routing
│   │   ├── useUrlDrivenExpansion.ts # URL-based accordion state
│   │   ├── useWorkflow.ts    # Workflow state management
│   │   ├── useFileUpload.ts  # File upload handling
│   │   └── useExport.ts      # Export functionality
│   ├── services/             # API communication layer
│   │   ├── api.ts           # LearnFlow API client
│   │   └── websocket.ts     # Real-time updates
│   ├── RouterWrapper.tsx     # Router configuration and routes
│   ├── AppWithRouter.tsx     # Main app with routing support
│   ├── types/               # TypeScript type definitions
│   └── utils/               # Helper utilities
├── public/                  # Static assets
└── docs/                    # Component documentation
```

### Navigation and Routing

The application features a comprehensive routing system with:

#### Deep Linking Support
- **Thread URLs**: `/thread/:threadId` - Direct access to specific threads
- **Session URLs**: `/thread/:threadId/session/:sessionId` - Direct session navigation
- **File URLs**: `/thread/:threadId/session/:sessionId/file/*` - Deep links to specific files
- **Browser Navigation**: Full back/forward button support with proper state management

#### URL-Driven State Management
- **Single Source of Truth**: URL contains all navigation state information
- **No localStorage Dependency**: Accordion expansion state derived from URL parameters
- **Tab Independence**: Each browser tab maintains independent navigation state
- **Shareable Links**: Users can bookmark and share links to specific content

#### Route Validation
- **API Integration**: Routes validated against backend data availability
- **Graceful Fallbacks**: Invalid URLs redirect to nearest valid navigation level
- **Loading States**: Proper loading indicators during route validation

### Integration with LearnFlow AI

The web UI integrates with the LearnFlow AI backend through:

#### REST API Endpoints
- `POST /process` - Submit educational questions for processing
- `POST /upload-images/{thread_id}` - Upload handwritten notes
- `GET /state/{thread_id}` - Retrieve workflow state
- `POST /export` - Generate PDF/Markdown exports

#### WebSocket Connection
- Real-time workflow progress updates
- HITL (Human-in-the-Loop) interaction notifications
- Live material generation streaming

#### Workflow Integration
The UI reflects the complete LangGraph workflow:
1. **Input Processing** - Question validation and categorization
2. **Content Generation** - Educational material creation
3. **OCR Recognition** - Handwritten note processing
4. **Material Synthesis** - Combining generated and recognized content
5. **Interactive Editing** - User-guided content refinement
6. **Gap Analysis** - Additional question generation
7. **Answer Generation** - Comprehensive answer creation
8. **Export** - Final material packaging

## Development

### Prerequisites
- Node.js 18+
- npm or yarn

### Setup
```bash
cd web-ui
npm install
```

### Development Server
```bash
npm run dev
# Available at http://localhost:5173
```

### Build for Production
```bash
npm run build
npm run preview  # Test production build
```

### Code Quality
```bash
npm run lint     # ESLint checks
npm run type-check  # TypeScript validation
```

## Configuration

### Environment Variables
```bash
# LearnFlow AI Backend
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws

# Feature Flags
VITE_ENABLE_EXPORT=true
VITE_ENABLE_WEBSOCKET=true
```

### Build Configuration
The UI is configured via `vite.config.ts` with:
- Hot Module Replacement (HMR) for fast development
- TypeScript compilation with strict mode
- ESLint integration for code quality
- CSS preprocessing and optimization

## Features by Subject Area

The UI adapts to different educational contexts:

### STEM Fields
- **Mathematics**: LaTeX rendering for equations and formulas
- **Physics**: Diagram embedding and scientific notation
- **Chemistry**: Molecular structure visualization
- **Computer Science**: Syntax highlighting for code examples

### Humanities
- **Literature**: Rich text formatting for essays and analysis
- **History**: Timeline visualization and source citation
- **Languages**: Multi-language character support

### Universal Features
- **Adaptive UI**: Context-aware component rendering
- **Accessibility**: WCAG 2.1 compliance with screen reader support
- **Responsive Design**: Mobile-first design for all device sizes
- **Dark/Light Mode**: Theme switching for user preference

## Deployment

### Docker
```bash
# Development
docker build -t learnflow-ui:dev .
docker run -p 5173:5173 learnflow-ui:dev

# Production
docker build -t learnflow-ui:prod --target production .
docker run -p 3000:3000 learnflow-ui:prod
```

### Static Hosting
Build artifacts in `dist/` can be deployed to:
- Netlify
- Vercel
- GitHub Pages
- AWS S3 + CloudFront

## Contributing

### Component Development
- Follow React functional component patterns
- Use TypeScript for all new code
- Implement proper error boundaries
- Write unit tests with React Testing Library

### UI Guidelines
- Maintain consistent spacing and typography
- Follow accessibility best practices
- Implement responsive design patterns
- Use semantic HTML elements

### Testing
```bash
npm run test        # Unit tests
npm run test:e2e    # End-to-end tests
npm run test:coverage  # Coverage report
```

The web UI provides a modern, accessible interface that makes LearnFlow AI's powerful educational content generation capabilities available to users across all subjects and education levels.