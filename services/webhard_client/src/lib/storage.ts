const TOKEN_KEY = "webhard.token";
const USERNAME_KEY = "webhard.username";

export const sessionStore = {
  save(token: string, username: string): void {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USERNAME_KEY, username);
  },
  load(): { token: string | null; username: string | null } {
    return {
      token: localStorage.getItem(TOKEN_KEY),
      username: localStorage.getItem(USERNAME_KEY),
    };
  },
  clear(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
  },
};
