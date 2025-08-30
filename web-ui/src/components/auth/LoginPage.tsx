import React, { useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useAuthGuard } from '../../hooks/useAuthGuard';
import { Button } from '../ui';
import { Input } from '../ui';
import { Card } from '../ui';
import '../../styles/login.css';

export const LoginPage: React.FC = () => {
  const [username, setUsername] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showError, setShowError] = useState(false);
  const { login } = useAuth();
  
  // Redirect if already authenticated
  useAuthGuard(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    // Validate input
    if (!username.trim() || !code.trim()) {
      setError('Пожалуйста, заполните все поля');
      return;
    }

    if (code.length !== 6) {
      setError('Код должен состоять из 6 символов');
      return;
    }

    setIsSubmitting(true);
    
    try {
      await login(username, code);
      // Redirect will happen automatically in AuthContext
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка авторизации');
      setShowError(true);
      setTimeout(() => setShowError(false), 400);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-form-wrapper">
        <Card variant="elevated" className="login-card">
          <div className="text-center mb-6">
            <div className="inline-flex items-center justify-center w-16 h-16 mb-4 rounded-sm bg-primary/10 border border-primary/20">
              <svg className="w-8 h-8 text-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25" />
              </svg>
            </div>
            <h1 className="text-2xl font-display font-bold text-ink mb-2 tracking-tight">
              LearnFlow AI
            </h1>
            <p className="text-base text-muted">
              Авторизуйтесь для доступа к материалам
            </p>
          </div>

          <div className="instruction-section">
            <div className="instruction-card">
              <h3 className="instruction-title">
                Как получить код доступа
              </h3>
              <ol className="instruction-list">
                <li>
                  <span className="instruction-number">1</span>
                  <span>Откройте <strong>@LearnFlowBot</strong> в Telegram</span>
                </li>
                <li>
                  <span className="instruction-number">2</span>
                  <span>Отправьте команду <code className="command-code">/web_auth</code></span>
                </li>
                <li>
                  <span className="instruction-number">3</span>
                  <span>Скопируйте 6-значный код из чата <span className="text-muted">(действует 5 минут)</span></span>
                </li>
                <li>
                  <span className="instruction-number">4</span>
                  <span>Введите username и код ниже</span>
                </li>
              </ol>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="form-section">
            <div className="form-field">
              <label htmlFor="username" className="form-label">
                Username
              </label>
              <Input
                id="username"
                type="text"
                placeholder="user_123456"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={isSubmitting}
                autoComplete="username"
                className="form-input"
                autoFocus
              />
              <p className="form-hint">
                user_XXXXXX (как в боте)
              </p>
            </div>

            <div className="form-field">
              <label htmlFor="code" className="form-label">
                Код авторизации
              </label>
              <div className="code-input-wrapper">
                <Input
                  id="code"
                  type="text"
                  placeholder="123456"
                  value={code}
                  onChange={(e) => setCode(e.target.value.slice(0, 6))}
                  disabled={isSubmitting}
                  autoComplete="one-time-code"
                  className="code-input"
                  maxLength={6}
                />
                <div className="code-dots">
                  {[...Array(6)].map((_, i) => (
                    <div
                      key={i}
                      className={`code-dot ${
                        i < code.length ? 'active' : ''
                      }`}
                    />
                  ))}
                </div>
              </div>
            </div>

            {error && (
              <div className={`error-message ${showError ? 'error-shake' : ''}`}>
                {error}
              </div>
            )}

            <Button
              type="submit"
              variant="primary"
              size="lg"
              disabled={isSubmitting || !username.trim() || code.length !== 6}
              className="submit-button"
              loading={isSubmitting}
            >
              {isSubmitting ? 'Проверка кода...' : 'Войти'}
            </Button>
          </form>

          <div className="footer-section">
            <p className="footer-text">
              Токен действует 24 часа. После истечения потребуется повторная авторизация.
            </p>
          </div>
        </Card>
      </div>
    </div>
  );
};