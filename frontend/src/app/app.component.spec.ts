import { fireEvent, render, screen } from '@testing-library/angular';
import { AppComponent } from './app.component';
import { AuthService } from './core/auth.service';
import { ApiService } from './core/api.service';

describe('AppComponent', () => {
  const providers = [
    { provide: AuthService, useValue: {
      token: () => null,
      csrfToken: () => null,
      restoreCsrfToken: () => false
    } },
    { provide: ApiService, useValue: {} }
  ];

  it('renders the CaseCraft sign-in workspace', async () => {
    await render(AppComponent, { providers });
    expect(screen.getByRole('heading', { name: 'Sign in to CaseCraft' })).toBeTruthy();
    expect(screen.getByRole('textbox', { name: 'Work email' })).toBeTruthy();
  });

  it('switches between sign-in and account creation', async () => {
    await render(AppComponent, { providers });
    fireEvent.click(screen.getByRole('button', { name: 'Create an account' }));
    expect(screen.getByRole('heading', { name: 'Start your workspace' })).toBeTruthy();
    expect(screen.getByRole('textbox', { name: 'Full name' })).toBeTruthy();
  });
});
