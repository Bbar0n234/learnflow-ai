import React, { useState } from 'react';
import { useAuth } from '../../hooks/useAuth';
import { useAuthGuard } from '../../hooks/useAuthGuard';
import { Button } from '../ui';
import { Input } from '../ui';
import { Card } from '../ui';

export const LoginPage: React.FC = () => {
  const [username, setUsername] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
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
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <Card className="w-full max-w-md p-8">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold mb-2">Вход в LearnFlow AI</h1>
          <p className="text-gray-600 dark:text-gray-400">
            Для доступа к материалам необходима авторизация
          </p>
        </div>

        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 mb-6">
          <h3 className="font-semibold mb-2 text-blue-900 dark:text-blue-100">
            Как получить код доступа:
          </h3>
          <ol className="space-y-2 text-sm text-blue-800 dark:text-blue-200">
            <li>1. Откройте @LearnFlowBot в Telegram</li>
            <li>2. Отправьте команду <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">/web_auth</code></li>
            <li>3. Бот отправит вам 6-значный код (действителен 5 минут)</li>
            <li>4. Введите ваш username и код ниже</li>
          </ol>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="username" className="block text-sm font-medium mb-1">
              Username из Telegram
            </label>
            <Input
              id="username"
              type="text"
              placeholder="user_123456"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isSubmitting}
              autoComplete="username"
              className="w-full"
            />
            <p className="text-xs text-gray-500 mt-1">
              Формат: user_XXXXXX (как в боте)
            </p>
          </div>

          <div>
            <label htmlFor="code" className="block text-sm font-medium mb-1">
              Код авторизации
            </label>
            <Input
              id="code"
              type="text"
              placeholder="123456"
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              disabled={isSubmitting}
              autoComplete="one-time-code"
              className="w-full font-mono text-lg tracking-wider text-center"
              maxLength={6}
            />
          </div>

          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 px-4 py-3 rounded-lg text-sm">
              {error}
            </div>
          )}

          <Button
            type="submit"
            disabled={isSubmitting || !username || code.length !== 6}
            className="w-full"
          >
            {isSubmitting ? 'Проверка кода...' : 'Войти'}
          </Button>
        </form>

        <div className="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <p className="text-xs text-center text-gray-500 dark:text-gray-400">
            После входа токен действителен 24 часа. При истечении потребуется повторная авторизация.
          </p>
        </div>
      </Card>
    </div>
  );
};