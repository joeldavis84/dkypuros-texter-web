import { Component, DestroyRef, ElementRef, ViewChild, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { bootstrapApplication } from '@angular/platform-browser';
import { HttpClient, HttpErrorResponse, provideHttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { EMPTY, Subject, catchError, exhaustMap, filter, merge, take, timeout, timer } from 'rxjs';

interface Message { id: number; sender: string; recipient: string; body: string; status: string; created_at: string; sip_branch: string | null; }
interface UeInfo { available: boolean; imsi: string | null; pdu_sessions: { id: number; dnn: string }[]; }

@Component({
  selector: 'app-root', standalone: true, imports: [FormsModule, DatePipe],
  template: `
    <main class="mx-auto max-w-5xl px-6 py-12">
      <header class="mb-10"><p class="text-sm font-semibold uppercase tracking-widest text-teal-700">5G / Network automation</p>
        <h1 class="mt-3 text-4xl font-bold">5G messaging automation</h1>
        <p class="mt-3 text-slate-600">Explore IMS messaging workflows for 5G network automation.</p>
      </header>
      <details class="mb-8 rounded-2xl border border-slate-200 bg-white p-6">
        <summary class="cursor-pointer text-xl font-semibold">UE configuration</summary>
        <div class="mt-4">
        @if (ueInfo(); as ue) {
          @if (ue.available) {
            <p class="mb-4"><span class="text-slate-500">IMSI</span> <span class="ml-3 break-all font-mono">{{ ue.imsi }}</span></p>
            <table class="w-full text-left">
              <thead><tr><th scope="col" class="pb-2">PDU ID</th><th scope="col" class="pb-2">PDU DNN</th></tr></thead>
              <tbody>
                @for (session of ue.pdu_sessions; track $index) {
                  <tr class="border-t border-slate-100"><td class="py-2">{{ session.id }}</td><td class="break-all py-2">{{ session.dnn }}</td></tr>
                } @empty { <tr><td colspan="2" class="py-2 text-slate-500">No PDU sessions configured.</td></tr> }
              </tbody>
            </table>
          } @else { <p class="text-slate-500">UE configuration is unavailable.</p> }
        } @else { <p role="status" class="text-slate-500">{{ ueInfoError() || 'Loading UE configuration…' }}</p> }
        </div>
      </details>
      <p role="alert" class="mb-4 text-red-700">{{ error() }}</p>
      <div class="grid gap-8 md:grid-cols-2">
        <section class="rounded-2xl border border-slate-200 bg-white p-6">
          <h2 class="mb-5 text-xl font-semibold">Send a message</h2>
          <form (ngSubmit)="submit()" #form="ngForm" class="space-y-5">
            <div>
              <p>Sender</p>
              <p class="mt-1 break-all font-medium">{{ sender() ? displayAddress(sender()) : 'Loading SIP account…' }}</p>
              <input type="hidden" name="sender" [value]="sender()">
            </div>
            <label class="block">Recipient<input name="recipient" [(ngModel)]="recipient" required maxlength="128" placeholder="bob@example.test"></label>
            <label class="block">Message<textarea name="body" [(ngModel)]="body" required maxlength="1600" rows="4" placeholder="Hello from the IMS demo"></textarea></label>
            <button type="submit" [disabled]="form.invalid || saving() || !sender()" class="rounded-lg bg-teal-700 px-5 py-3 font-semibold text-white">{{ saving() ? 'Working…' : 'Send message' }}</button>
          </form>
        </section>
        <section class="rounded-2xl border border-slate-200 bg-white p-6">
          <div class="mb-5 flex items-center justify-between"><h2 class="text-xl font-semibold">Recent messages</h2><button type="button" (click)="refresh()" class="text-teal-700">Refresh</button></div>
          <p class="mb-4 text-sm text-slate-500">Latest 20 messages · Checks for updates every 5 seconds</p>
          <p role="status" class="mb-4 text-red-700">{{ messagesError() }}</p>
          @for (message of messages(); track message.id) {
            <article class="border-t border-slate-100 py-4">
              <div class="flex items-start justify-between gap-3"><h3 class="min-w-0 break-all font-bold" [attr.title]="message.sip_branch ? 'SIP branch: ' + message.sip_branch : 'SIP branch unavailable'">{{ displayAddress(message.sender) }} → {{ displayAddress(message.recipient) }}</h3><span class="shrink-0 rounded bg-teal-50 px-2 text-sm text-teal-800">{{ message.status }}</span></div>
              <time class="mt-1 block text-xs text-slate-500" [attr.datetime]="message.created_at">{{ message.created_at | date:'MMM d, y, h:mm:ss a z' }}</time>
              <p class="mt-2 whitespace-pre-wrap break-words">{{ message.body }}</p>
            </article>
          } @empty { <p class="py-8 text-slate-500">No messages loaded. Send or receive a SIP text message.</p> }
        </section>
      </div>
    </main>
    <dialog #workingDialog aria-labelledby="working-title" aria-describedby="working-description"
      (cancel)="$event.preventDefault()"
      class="m-auto rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-xl backdrop:bg-black/40">
      <div role="status" aria-live="polite" aria-busy="true">
        <h2 id="working-title" class="text-xl font-semibold">Working</h2>
        <progress aria-label="Sending message" class="my-5 h-2 w-48 accent-teal-700"></progress>
        <p id="working-description" class="text-sm text-slate-600">Waiting for SIP to accept your message…</p>
      </div>
    </dialog>`
})
class AppComponent {
  private http = inject(HttpClient);
  private destroyRef = inject(DestroyRef);
  @ViewChild('workingDialog') private workingDialog!: ElementRef<HTMLDialogElement>;
  private refreshRequests = new Subject<void>();
  messages = signal<Message[]>([]);
  messagesError = signal('');
  saving = signal(false);
  error = signal('');
  sender = signal('');
  ueInfo = signal<UeInfo | null>(null);
  ueInfoError = signal('');
  recipient = ''; body = '';
  constructor() {
    this.http.get<UeInfo>('/api/v1/ue-info').pipe(
      timeout(10000), takeUntilDestroyed()
    ).subscribe({
      next: info => this.ueInfo.set(info),
      error: () => this.ueInfoError.set('Unable to load UE configuration.')
    });
    this.http.get<{ account_uri: string; enabled: boolean }>('/api/v1/sip-account').pipe(
      takeUntilDestroyed()
    ).subscribe({
      next: account => {
        this.sender.set(account.enabled ? account.account_uri : '');
        if (!account.enabled) this.error.set('Configure a SIP account on this instance before sending.');
      },
      error: () => this.error.set('Cannot load the SIP account. Reload the page to try again.')
    });
    merge(timer(0, 5000), this.refreshRequests).pipe(
      // Keep at most one request in flight, including manual refreshes.
      exhaustMap(() => this.http.get<{ messages: Message[] }>('/api/v1/messages').pipe(
        timeout(10000),
        catchError(() => {
          this.messagesError.set('Cannot refresh messages. Retrying automatically…');
          return EMPTY;
        })
      )),
      takeUntilDestroyed()
    ).subscribe(result => {
      this.messagesError.set('');
      // Leave existing DOM and form state alone when the list is unchanged.
      if (JSON.stringify(result.messages) !== JSON.stringify(this.messages())) {
        this.messages.set(result.messages);
      }
    });
  }
  refresh() { this.refreshRequests.next(); }
  displayAddress(address: string) {
    return address.trim().replace(/^<([^>]+)>$/, '$1').replace(/(^|<)sip:/gi, '$1');
  }
  private finishSending(error = '') {
    this.saving.set(false);
    this.workingDialog.nativeElement.close();
    this.error.set(error);
    this.refresh();
  }
  private watchSend(messageId: number) {
    // Use the detail endpoint: outgoing self-messages are hidden from Recent messages.
    timer(0, 1000).pipe(
      exhaustMap(() => this.http.get<Message>('/api/v1/messages/' + messageId).pipe(timeout(10000))),
      filter(message => !['queued', 'sending'].includes(message.status)),
      take(1),
      timeout(60000),
      takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: message => {
        if (message.status === 'sent') {
          this.finishSending();
        } else if (message.status === 'failed') {
          this.finishSending('SIP could not send the message. Check Recent messages for its status.');
        } else {
          this.finishSending('SIP did not confirm acceptance. The message may have been sent; check its status before retrying.');
        }
      },
      error: () => this.finishSending('Could not confirm SIP acceptance. The message may still be queued or sent; check its status before retrying.')
    });
  }
  submit() {
    if (this.saving() || !this.sender()) return;
    this.saving.set(true); this.error.set('');
    this.workingDialog.nativeElement.showModal();
    const recipient = 'sip:' + this.recipient.trim().replace(/^sip:/i, '');
    this.http.post<Message>('/api/v1/messages', { sender: this.sender(), recipient, body: this.body }).pipe(
      timeout(10000), takeUntilDestroyed(this.destroyRef)
    ).subscribe({
      next: message => { this.body = ''; this.refresh(); this.watchSend(message.id); },
      error: (err: HttpErrorResponse) => this.finishSending(err.error?.error?.message ?? 'Could not confirm submission. Check Recent messages before trying again.')
    });
  }
}

const backgroundColors = ['#32a852', '#f0959b', '#9592f7', '#ffffff', '#fa5eff'];
document.body.style.backgroundColor = backgroundColors[Math.floor(Math.random() * backgroundColors.length)]!;

bootstrapApplication(AppComponent, { providers: [provideHttpClient()] }).catch(console.error);
