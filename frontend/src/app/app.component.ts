import { Component, computed, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { finalize } from 'rxjs';
import { ApiService } from './core/api.service';
import { AuthService } from './core/auth.service';
import { Dashboard, Project, Requirement, TestCase } from './core/models';

@Component({
  selector: 'cc-root',
  standalone: true,
  imports: [CommonModule, FormsModule, MatButtonModule, MatFormFieldModule, MatIconModule, MatInputModule, MatProgressSpinnerModule],
  template: `
    <div class="shell" [class.dark]="darkMode()">
      <header class="topbar">
        <a class="brand" href="/" aria-label="CaseCraft QA home"><span class="brand-mark">C</span><span>casecraft<span class="brand-light">.qa</span></span></a>
        <div class="top-actions">
          @if (auth.token()) { <span class="live-label"><i></i> Workspace</span> }
          <button class="icon-button" type="button" aria-label="Toggle dark mode" (click)="darkMode.set(!darkMode())"><mat-icon>{{ darkMode() ? 'light_mode' : 'dark_mode' }}</mat-icon></button>
          @if (auth.token()) { <button mat-button class="signout" (click)="logout()">Sign out</button> }
        </div>
      </header>

      @if (!auth.token() && busy()) {
        <main class="auth-layout"><div class="loading"><mat-spinner diameter="32"></mat-spinner><span>Restoring your secure session…</span></div></main>
      } @else if (!auth.token()) {
        <main class="auth-layout">
          <section class="hero">
            <div class="eyebrow"><span class="spark">✳</span> QUALITY, AT THE SPEED OF THOUGHT</div>
            <h1>Turn requirements<br>into <em>confidence.</em></h1>
            <p class="hero-copy">A thoughtful workspace for teams who believe great software starts with great testing.</p>
            <div class="hero-points">
              <span><mat-icon>auto_awesome</mat-icon> AI-crafted test coverage</span>
              <span><mat-icon>account_tree</mat-icon> Traceable to every requirement</span>
              <span><mat-icon>verified_user</mat-icon> Built for your team's workflow</span>
            </div>
            <div class="hero-note">Designed for the details that matter.</div>
          </section>
          <section class="auth-card">
            <div class="card-kicker">{{ registering() ? 'CREATE YOUR ACCOUNT' : 'WELCOME BACK' }}</div>
            <h2>{{ registering() ? 'Start your workspace' : 'Sign in to CaseCraft' }}</h2>
            <p class="muted">{{ registering() ? 'Create your account and bring clarity to testing.' : 'Your quality workspace is ready when you are.' }}</p>
            <form (ngSubmit)="submitAuth()" #authForm="ngForm">
              @if (registering()) {
                <mat-form-field appearance="outline"><mat-label>Full name</mat-label><input matInput name="fullName" [(ngModel)]="fullName" required autocomplete="name"></mat-form-field>
              }
              <mat-form-field appearance="outline"><mat-label>Work email</mat-label><input matInput name="email" type="email" [(ngModel)]="email" required autocomplete="email"></mat-form-field>
              <mat-form-field appearance="outline"><mat-label>Password</mat-label><input matInput name="password" type="password" [(ngModel)]="password" required [minlength]="registering() ? 12 : 1" autocomplete="current-password"></mat-form-field>
              @if (error()) { <div class="error" role="alert">{{ error() }}</div> }
              <button mat-flat-button color="primary" class="primary-button" [disabled]="busy() || authForm.invalid">
                {{ registering() ? 'Create account' : 'Sign in' }} <mat-icon>arrow_forward</mat-icon>
              </button>
            </form>
            <div class="auth-switch">{{ registering() ? 'Already have an account?' : 'New to CaseCraft?' }}
              <button type="button" (click)="registering.set(!registering()); error.set('')">{{ registering() ? 'Sign in' : 'Create an account' }}</button>
            </div>
            <div class="secure-note"><mat-icon>lock</mat-icon> Secure access · Your data stays yours</div>
          </section>
          <footer class="auth-footer"><span>© 2026 CaseCraft QA</span><span>Made for teams that care about quality.</span></footer>
        </main>
      } @else {
        <main class="workspace">
          <aside class="sidebar">
            <div class="side-section">WORKSPACE</div>
            <button class="nav-link active"><mat-icon>space_dashboard</mat-icon> Overview</button>
            <button class="nav-link" (click)="requirementPanel.set(!requirementPanel())"><mat-icon>description</mat-icon> Requirements</button>
            <button class="nav-link" (click)="casePanel.set(!casePanel())"><mat-icon>fact_check</mat-icon> Test cases</button>
            <div class="side-section projects-label">YOUR PROJECTS</div>
            @for (project of projects(); track project.id) {
              <button class="project-link" [class.selected]="selectedProject()?.id === project.id" (click)="selectProject(project)">
                <span class="project-dot">{{ project.name.slice(0, 1).toUpperCase() }}</span>{{ project.name }}
              </button>
            }
            <button class="new-project-link" (click)="projectPanel.set(!projectPanel())"><mat-icon>add</mat-icon> New project</button>
            <div class="sidebar-bottom"><span class="avatar">{{ userInitials() }}</span><span><b>My workspace</b><small>QA team</small></span><mat-icon>more_horiz</mat-icon></div>
          </aside>
          <section class="main-content">
            <div class="page-heading">
              <div><div class="breadcrumb">WORKSPACE <span>/</span> OVERVIEW</div><h1>{{ selectedProject()?.name || 'Your quality workspace' }}</h1><p>Here's what's happening across your test coverage.</p></div>
              <div class="heading-actions">
                @if (selectedProject()) {
                  <button class="secondary-button" (click)="exportCases()"><mat-icon>download</mat-icon> Export</button>
                  <button class="primary-cta" (click)="requirementPanel.set(!requirementPanel())"><mat-icon>add</mat-icon> Add requirement</button>
                }
              </div>
            </div>
            @if (projectPanel()) {
              <form class="inline-form" (ngSubmit)="createProject()">
                <input aria-label="Project name" placeholder="Project name" [(ngModel)]="projectName" name="projectName" required>
                <input aria-label="Project description" placeholder="Description (optional)" [(ngModel)]="projectDescription" name="projectDescription">
                <button class="primary-cta" type="submit">Create project</button>
              </form>
            }
            @if (requirementPanel() && selectedProject()) {
              <form class="requirement-form" (ngSubmit)="createRequirement()">
                <div class="form-title"><div><span class="card-kicker">REQUIREMENT INTAKE</span><h2>Add a requirement</h2></div><button class="icon-button" type="button" aria-label="Close form" (click)="requirementPanel.set(false)"><mat-icon>close</mat-icon></button></div>
                <div class="form-grid"><input aria-label="Requirement ID" placeholder="Requirement ID (e.g. AUTH-101)" [(ngModel)]="requirementKey" name="requirementKey" required>
                  <input aria-label="Requirement title" placeholder="Short title" [(ngModel)]="requirementTitle" name="requirementTitle" required></div>
                <textarea aria-label="Requirement description" placeholder="Describe the user story or business requirement..." [(ngModel)]="requirementDescription" name="requirementDescription" required></textarea>
                <textarea aria-label="Acceptance criteria" placeholder="Acceptance criteria (optional)" [(ngModel)]="acceptanceCriteria" name="acceptanceCriteria"></textarea>
                <div class="form-footer"><span class="muted">AI generation uses requirement details to create traceable scenarios.</span><button class="primary-cta" type="submit" [disabled]="busy()"><mat-icon>auto_awesome</mat-icon> Save & generate tests</button></div>
                <input #requirementUpload hidden type="file" accept=".pdf,.docx,.txt,.csv,.xlsx" (change)="uploadRequirement($event)">
                <button class="secondary-button upload-button" type="button" (click)="requirementUpload.click()"><mat-icon>upload_file</mat-icon> Import document</button>
              </form>
            }
            @if (error()) { <div class="error workspace-error" role="alert">{{ error() }}</div> }
            @if (dashboard(); as stats) {
              <div class="metrics-grid">
                <article class="metric-card"><div class="metric-top"><span>Total requirements</span><mat-icon>description</mat-icon></div><strong>{{ stats.total_requirements }}</strong><small>In this project</small></article>
                <article class="metric-card"><div class="metric-top"><span>Test cases</span><mat-icon>fact_check</mat-icon></div><strong>{{ stats.total_test_cases }}</strong><small>Across all requirements</small></article>
                <article class="metric-card"><div class="metric-top"><span>Coverage</span><mat-icon>donut_large</mat-icon></div><strong>{{ stats.coverage_percent }}<small class="percent">%</small></strong><div class="progress-track"><span [style.width.%]="stats.coverage_percent"></span></div></article>
                <article class="metric-card"><div class="metric-top"><span>Automation readiness</span><mat-icon>smart_toy</mat-icon></div><strong>{{ stats.automation_readiness_percent }}<small class="percent">%</small></strong><small>High feasibility</small></article>
              </div>
              <div class="overview-grid">
                <article class="panel priority-panel"><div class="panel-heading"><div><span class="card-kicker">TEST DISTRIBUTION</span><h2>Priority overview</h2></div><mat-icon>more_horiz</mat-icon></div>
                  @for (priority of ['P0', 'P1', 'P2']; track priority) {
                    <div class="priority-row"><span class="priority-badge" [class]="priority.toLowerCase()">{{ priority }}</span><div class="priority-track"><span [class]="priority.toLowerCase()" [style.width.%]="priorityPercent(stats, priority)"></span></div><b>{{ stats.priority_distribution[priority] }}</b></div>
                  }
                  <div class="panel-foot"><span>{{ stats.duplicate_test_cases }} duplicate scenarios detected</span><mat-icon>info_outline</mat-icon></div>
                </article>
                <article class="panel coverage-panel"><div class="panel-heading"><div><span class="card-kicker">REQUIREMENT HEALTH</span><h2>Coverage snapshot</h2></div><span class="health-pill"><i></i> On track</span></div>
                  <div class="coverage-number">{{ stats.covered_requirements }} <span>of {{ stats.total_requirements }} requirements covered</span></div>
                  <div class="progress-track large"><span [style.width.%]="stats.coverage_percent"></span></div>
                  <div class="coverage-note"><mat-icon>lightbulb</mat-icon><span>Defect prediction score: <b>{{ stats.defect_prediction_score }}</b> — use this signal to focus review effort.</span></div>
                </article>
              </div>
            } @else if (busy()) { <div class="loading"><mat-spinner diameter="32"></mat-spinner><span>Loading your workspace…</span></div> }
            @if (selectedProject()) {
              <section class="panel data-panel">
                <div class="panel-heading"><div><span class="card-kicker">TRACEABILITY</span><h2>{{ casePanel() ? 'Generated test cases' : 'Requirements' }}</h2></div>
                  <div class="search-wrap"><mat-icon>search</mat-icon><input aria-label="Search test cases" placeholder="Search scenarios…" [(ngModel)]="searchText" (ngModelChange)="loadCases()"></div>
                </div>
                @if (!casePanel()) {
                  @for (requirement of requirements(); track requirement.id) {
                    <button class="requirement-row" (click)="generate(requirement)"><span class="requirement-id">{{ requirement.requirement_key }}</span><span class="requirement-name">{{ requirement.title }}</span><span class="generate-link"><mat-icon>auto_awesome</mat-icon> Generate tests</span></button>
                  } @empty { <div class="empty-state">No requirements yet. Add one to start generating traceable tests.</div> }
                } @else {
                  @for (testCase of testCases(); track testCase.id) {
                    <article class="case-row"><div><b>{{ testCase.case_key }}</b><p>{{ testCase.scenario }}</p><small>{{ testCase.test_type }} · {{ testCase.automation_feasibility }} automation</small></div><span class="priority-badge" [class]="testCase.priority.toLowerCase()">{{ testCase.priority }}</span></article>
                  } @empty { <div class="empty-state">No test cases match your search.</div> }
                }
              </section>
            } @else if (!busy()) { <section class="empty-project"><div class="empty-icon"><mat-icon>folder_open</mat-icon></div><h2>Create your first project</h2><p>Bring requirements and test coverage together in one place.</p><button class="primary-cta" (click)="projectPanel.set(true)"><mat-icon>add</mat-icon> New project</button></section> }
          </section>
        </main>
      }
    </div>
  `,
  styleUrl: './app.component.scss'
})
export class AppComponent implements OnInit {
  readonly darkMode = signal(false);
  readonly registering = signal(false);
  readonly projects = signal<Project[]>([]);
  readonly selectedProject = signal<Project | null>(null);
  readonly requirements = signal<Requirement[]>([]);
  readonly testCases = signal<TestCase[]>([]);
  readonly dashboard = signal<Dashboard | null>(null);
  readonly requirementPanel = signal(false);
  readonly casePanel = signal(false);
  readonly projectPanel = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly userInitials = computed(() => this.fullName ? this.fullName.slice(0, 1).toUpperCase() : 'Q');

  email = '';
  password = '';
  fullName = '';
  projectName = '';
  projectDescription = '';
  requirementKey = '';
  requirementTitle = '';
  requirementDescription = '';
  acceptanceCriteria = '';
  searchText = '';

  constructor(readonly auth: AuthService, readonly api: ApiService) {}

  ngOnInit(): void {
    if (!this.auth.restoreCsrfToken()) return;
    this.busy.set(true);
    this.auth.refresh().pipe(finalize(() => this.busy.set(false))).subscribe({
      next: () => this.loadProjects(),
      error: (error: HttpErrorResponse) => {
        this.auth.clear();
        if (error.status !== 401) this.error.set(this.errorMessage(error));
      }
    });
  }

  submitAuth(): void {
    this.error.set('');
    this.busy.set(true);
    const request = this.registering()
      ? this.auth.register(this.email, this.fullName, this.password)
      : this.auth.login(this.email, this.password);
    request.pipe(finalize(() => this.busy.set(false))).subscribe({
      next: () => this.loadProjects(),
      error: (error: HttpErrorResponse) => this.error.set(this.errorMessage(error))
    });
  }

  logout(): void {
    this.auth.logout().subscribe({ error: () => this.auth.clear() });
  }

  loadProjects(): void {
    this.busy.set(true);
    this.api.projects().pipe(finalize(() => this.busy.set(false))).subscribe({
      next: projects => {
        this.projects.set(projects);
        if (projects.length) this.selectProject(projects[0]);
      },
      error: (error: HttpErrorResponse) => this.error.set(this.errorMessage(error))
    });
  }

  selectProject(project: Project): void {
    this.selectedProject.set(project);
    this.casePanel.set(false);
    this.api.requirements(project.id).subscribe({
      next: rows => this.requirements.set(rows),
      error: error => this.error.set(this.errorMessage(error))
    });
    this.api.dashboard(project.id).subscribe({
      next: stats => this.dashboard.set(stats),
      error: error => this.error.set(this.errorMessage(error))
    });
    this.loadCases();
  }

  createProject(): void {
    if (!this.projectName.trim()) return;
    this.busy.set(true);
    this.api.createProject(this.projectName.trim(), this.projectDescription.trim())
      .pipe(finalize(() => this.busy.set(false))).subscribe({
        next: project => {
          this.projects.update(items => [project, ...items]);
          this.projectName = '';
          this.projectDescription = '';
          this.projectPanel.set(false);
          this.selectProject(project);
        },
        error: error => this.error.set(this.errorMessage(error))
      });
  }

  createRequirement(): void {
    const project = this.selectedProject();
    if (!project || !this.requirementKey.trim() || !this.requirementTitle.trim() || !this.requirementDescription.trim()) return;
    this.busy.set(true);
    this.api.createRequirement(project.id, {
      requirement_key: this.requirementKey.trim(),
      title: this.requirementTitle.trim(),
      description: this.requirementDescription.trim(),
      acceptance_criteria: this.acceptanceCriteria.trim()
    }).pipe(finalize(() => this.busy.set(false))).subscribe({
      next: requirement => {
        this.requirements.update(items => [requirement, ...items]);
        this.requirementPanel.set(false);
        this.requirementKey = '';
        this.requirementTitle = '';
        this.requirementDescription = '';
        this.acceptanceCriteria = '';
        this.generate(requirement);
        this.refreshDashboard();
      },
      error: error => this.error.set(this.errorMessage(error))
    });
  }

  generate(requirement: Requirement): void {
    this.error.set('');
    this.busy.set(true);
    this.api.generate(requirement.id).pipe(finalize(() => this.busy.set(false))).subscribe({
      next: cases => {
        this.testCases.update(existing => [...cases, ...existing]);
        this.casePanel.set(true);
        this.refreshDashboard();
      },
      error: error => this.error.set(this.errorMessage(error))
    });
  }

  uploadRequirement(event: Event): void {
    const project = this.selectedProject();
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!project || !file) return;
    this.error.set('');
    this.busy.set(true);
    if (file.name.toLowerCase().endsWith('.csv')) {
      this.api.importRequirementsCsv(project.id, file).pipe(finalize(() => {
        this.busy.set(false);
        input.value = '';
      })).subscribe({
        next: result => {
          this.requirements.update(items => [...result.requirements, ...items]);
          this.refreshDashboard();
        },
        error: error => this.error.set(this.errorMessage(error))
      });
      return;
    }
    this.api.uploadRequirement(project.id, file).pipe(finalize(() => {
      this.busy.set(false);
      input.value = '';
    })).subscribe({
      next: requirement => {
        this.requirements.update(items => [requirement, ...items]);
        this.refreshDashboard();
        this.generate(requirement);
      },
      error: error => this.error.set(this.errorMessage(error))
    });
  }

  exportCases(): void {
    const project = this.selectedProject();
    if (!project) return;
    this.api.export(project.id, 'xlsx').subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = 'test-cases.xlsx';
        anchor.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      },
      error: error => this.error.set(this.errorMessage(error))
    });
  }

  loadCases(): void {
    const project = this.selectedProject();
    if (!project) return;
    this.api.testCases(project.id, 1, this.searchText).subscribe({
      next: page => this.testCases.set(page.items),
      error: error => this.error.set(this.errorMessage(error))
    });
  }

  priorityPercent(stats: Dashboard, priority: string): number {
    const total = Object.values(stats.priority_distribution).reduce((sum, value) => sum + value, 0);
    return total ? (stats.priority_distribution[priority] / total) * 100 : 0;
  }

  private refreshDashboard(): void {
    const project = this.selectedProject();
    if (project) this.api.dashboard(project.id).subscribe({ next: stats => this.dashboard.set(stats) });
  }

  private errorMessage(error: HttpErrorResponse): string {
    if (typeof error.error?.detail === 'string') return error.error.detail;
    return error.status === 0 ? 'Unable to reach the service. Check the API connection and try again.' : 'The request could not be completed. Please try again.';
  }
}
