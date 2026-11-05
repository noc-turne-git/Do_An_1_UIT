# Password reset by email link

The forgot-password dialog sends an email and stays at its email-sent notice.
The email link returns to `/reset-password`, outside the home/app shell.
Only that route opens the new-password modal on `PASSWORD_RECOVERY`.
After saving, the modal shows a success message without navigating to home.
The original tab does not open a recovery modal in response to auth events.

## Required Supabase configuration

In Authentication email templates, open **Reset password**, use this body and save:

```html
<h2>Reset your Travelio password</h2>
<p>Follow this link to set a new password:</p>
<p><a href="{{ .ConfirmationURL }}">Reset password</a></p>
<p>If you did not request this, you can ignore this email.</p>
```

In Authentication > URL Configuration, allow the exact frontend URL ending in
`/reset-password`, for example `http://localhost:5173/reset-password` and the
corresponding production URL. Use the port where Vite actually runs.
Do not replace ConfirmationURL with a direct frontend link: the Supabase link
must verify the recovery token before redirecting to Travelio.
Request a fresh email after changing the template or redirect configuration.

## Manual verification

1. Request a reset for an existing account; the original tab stays at the sent notice.
2. Click the email link; the new tab opens `/reset-password` and the new-password form.
3. Mismatched passwords and update errors should keep the form open for retry.
4. Save a matching new password; a success message remains without entering home.
5. Check that the original tab still shows the sent notice, with no recovery modal.
6. Sign out and verify login with the new password.
7. Invalid or expired links must show an error instead of the password form.

Reference: https://supabase.com/docs/reference/javascript/auth-resetpasswordforemail
