import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, finalize, shareReplay, tap } from 'rxjs';
import { AuthResponse } from './models';

@Injectable({ providedIn: 'root' })
export class AuthService {
  readonly token = signal<string | null>(null);
  readonly csrfToken = signal<string | null>(null);
  private refreshRequest: Observable<AuthResponse> | null = null;

  constructor(private readonly http: HttpClient) {}

  login(email: string, password: string): Observable<AuthResponse> {
    return this.http.post<AuthResponse>('/api/v1/auth/login', { email, password }, { withCredentials: true })
      .pipe(tap(response => this.accept(response)));
  }

  register(email: string, full_name: string, password: string): Observable<AuthResponse> {
    return this.http.post<AuthResponse>('/api/v1/auth/register', { email, full_name, password }, { withCredentials: true })
      .pipe(tap(response => this.accept(response)));
  }

  restoreCsrfToken(): boolean {
    const cookie = document.cookie.split(';').map(value => value.trim())
      .find(value => value.startsWith('csrf_token='));
    if (!cookie) return false;
    this.csrfToken.set(decodeURIComponent(cookie.slice('csrf_token='.length)));
    return true;
  }

  logout(): Observable<void> {
    return this.http.post<void>('/api/v1/auth/logout', {}, {
      withCredentials: true,
      headers: { 'X-CSRF-Token': this.csrfToken() ?? '' }
    }).pipe(tap(() => this.clear()));
  }

  refresh(): Observable<AuthResponse> {
    if (!this.refreshRequest) {
      this.refreshRequest = this.http.post<AuthResponse>('/api/v1/auth/refresh', {}, {
        withCredentials: true,
        headers: { 'X-CSRF-Token': this.csrfToken() ?? '' }
      }).pipe(
        tap(response => this.accept(response)),
        finalize(() => this.refreshRequest = null),
        shareReplay({ bufferSize: 1, refCount: false })
      );
    }
    return this.refreshRequest;
  }

  clear(): void {
    this.token.set(null);
    this.csrfToken.set(null);
  }

  private accept(response: AuthResponse): void {
    this.token.set(response.access_token);
    this.csrfToken.set(response.csrf_token);
  }
}
