import { Component, inject, signal } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { HttpClient, HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';

interface Message { id: number; sender: string; recipient: string; body: string; status: string; created_at: string; }

@Component({
  selector: 'app-root', standalone: true, imports: [FormsModule],
  template: `
    <main class="mx-auto max-w-5xl px-6 py-12">
      <header class="mb-10"><p class="text-sm font-semibold uppercase tracking-widest text-teal-700">Duranta / IMS lab</p>
        <h1 class="mt-3 text-4xl font-bold">IMS text messaging</h1>
        <p class="mt-3 text-slate-600">Prepare message requests for your Duranta demo.</p>
      </header>
      <p class="mb-8 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-900">Simulation mode — requests are saved locally. No IMS messages are transmitted.</p>
      <p role="alert" class="mb-4 text-red-700">{{ error() }}</p>
      <div class="grid gap-8 md:grid-cols-2">
        <section class="rounded-2xl border border-slate-200 bg-white p-6">
          <h2 class="mb-5 text-xl font-semibold">Create a demo message</h2>
          <form (ngSubmit)="submit()" #form="ngForm" class="space-y-5">
            <label class="block">Sender<input name="sender" [(ngModel)]="sender" required maxlength="128" placeholder="sip:alice@example.test"></label>
            <label class="block">Recipient<input name="recipient" [(ngModel)]="recipient" required maxlength="128" placeholder="sip:bob@example.test"></label>
            <label class="block">Message<textarea name="body" [(ngModel)]="body" required maxlength="1600" rows="4" placeholder="Hello from the IMS demo"></textarea></label>
            <button type="submit" [disabled]="form.invalid || saving()" class="rounded-lg bg-teal-700 px-5 py-3 font-semibold text-white">{{ saving() ? 'Saving…' : 'Save simulated message' }}</button>
            <p role="status" class="text-sm text-teal-800">{{ notice() }}</p>
          </form>
        </section>
        <section class="rounded-2xl border border-slate-200 bg-white p-6">
          <div class="mb-5 flex items-center justify-between"><h2 class="text-xl font-semibold">Recent requests</h2><button type="button" (click)="refresh()" class="text-teal-700">Refresh</button></div>
          <p class="mb-4 text-sm text-slate-500">Latest 20 requests · API v1</p>
          @for (message of messages(); track message.id) {
            <article class="border-t border-slate-100 py-4">
              <div class="flex justify-between gap-3"><span class="font-medium">Request #{{ message.id }}</span><span class="rounded bg-teal-50 px-2 text-sm text-teal-800">{{ message.status }}</span></div>
              <p class="mt-2 break-all text-sm text-slate-500">{{ message.sender }} → {{ message.recipient }}</p>
              <p class="mt-2 whitespace-pre-wrap break-words">{{ message.body }}</p>
            </article>
          } @empty { <p class="py-8 text-slate-500">No requests loaded. Create your first demo message.</p> }
        </section>
      </div>
    </main>`
})
class AppComponent {
  private http = inject(HttpClient);
  messages = signal<Message[]>([]);
  saving = signal(false);
  error = signal('');
  notice = signal('');
  sender = ''; recipient = ''; body = '';
  constructor() { this.refresh(); }
  refresh() {
    this.error.set('');
    this.http.get<{ messages: Message[] }>('/api/v1/messages').subscribe({
      next: result => this.messages.set(result.messages),
      error: () => this.error.set('Cannot load requests. Check Flask and initialize the database.')
    });
  }
  submit() {
    this.saving.set(true); this.error.set(''); this.notice.set('');
    this.http.post<Message>('/api/v1/messages', { sender: this.sender, recipient: this.recipient, body: this.body }).subscribe({
      next: message => { this.saving.set(false); this.body = ''; this.notice.set('Simulated request #' + message.id + ' saved.'); this.refresh(); },
      error: (err: HttpErrorResponse) => { this.saving.set(false); this.error.set(err.error?.error?.message ?? 'Unable to save request. Check the API connection.'); }
    });
  }
}

bootstrapApplication(AppComponent, { providers: [provideHttpClient()] }).catch(console.error);
