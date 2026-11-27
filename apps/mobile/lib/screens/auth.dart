import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../core/app_lock.dart';
import '../core/config.dart';
import '../core/session.dart';
import '../core/ui.dart';

class _AuthScaffold extends StatelessWidget {
  const _AuthScaffold({required this.title, this.subtitle, required this.children});

  final String title;
  final String? subtitle;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Center(
                    child: Container(
                      width: 56,
                      height: 56,
                      decoration: BoxDecoration(
                        color: Brand.primary,
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: const Icon(Icons.shield_outlined, color: Colors.white, size: 30),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    AppConfig.productName,
                    textAlign: TextAlign.center,
                    style: theme.textTheme.labelLarge?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 24),
                  Text(title, style: theme.textTheme.headlineSmall),
                  if (subtitle != null) ...[
                    const SizedBox(height: 6),
                    Text(
                      subtitle!,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                  const SizedBox(height: 24),
                  ...children,
                  const SizedBox(height: 32),
                  const PoweredBy(),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ErrorBox extends StatelessWidget {
  const _ErrorBox(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.errorContainer,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Text(message, style: TextStyle(color: scheme.onErrorContainer)),
    );
  }
}

class SignInScreen extends StatefulWidget {
  const SignInScreen({super.key, required this.session});

  final Session session;

  @override
  State<SignInScreen> createState() => _SignInScreenState();
}

class _SignInScreenState extends State<SignInScreen> {
  final _identifier = TextEditingController();
  final _password = TextEditingController();
  final _code = TextEditingController();
  String? _mfaToken;
  String? _error;
  bool _busy = false;
  bool _obscure = true;

  @override
  void initState() {
    super.initState();
    _error = widget.session.endedMessage;
  }

  @override
  void dispose() {
    _identifier.dispose();
    _password.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_mfaToken == null && (_identifier.text.trim().isEmpty || _password.text.isEmpty)) {
      setState(() => _error = 'Enter your email or username and your password.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (_mfaToken == null) {
        final result = await widget.session.signIn(_identifier.text, _password.text);
        if (result is NeedsMfa && mounted) setState(() => _mfaToken = result.mfaToken);
      } else {
        await widget.session.verifyMfa(_mfaToken!, _code.text);
      }
    } on ApiException catch (e) {
      if (e.code == 'mfa_token_expired') _mfaToken = null;
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_mfaToken != null) {
      return _AuthScaffold(
        title: 'Two-step verification',
        subtitle: 'Enter the 6-digit code from your authenticator app, or a recovery code.',
        children: [
          if (_error != null) _ErrorBox(_error!),
          TextField(
            key: const Key('mfa-code'),
            controller: _code,
            autofocus: true,
            keyboardType: TextInputType.number,
            autofillHints: const [AutofillHints.oneTimeCode],
            decoration: const InputDecoration(labelText: 'Code'),
            onSubmitted: (_) => _submit(),
          ),
          const SizedBox(height: 16),
          FilledButton(
            onPressed: _busy ? null : _submit,
            child: Text(_busy ? 'Checking…' : 'Verify'),
          ),
          TextButton(
            onPressed: _busy ? null : () => setState(() => _mfaToken = null),
            child: const Text('Back'),
          ),
        ],
      );
    }
    return _AuthScaffold(
      title: 'Sign in',
      subtitle: 'Use the same account as the web dashboard.',
      children: [
        if (_error != null) _ErrorBox(_error!),
        AutofillGroup(
          child: Column(
            children: [
              TextField(
                key: const Key('identifier'),
                controller: _identifier,
                autocorrect: false,
                keyboardType: TextInputType.emailAddress,
                autofillHints: const [AutofillHints.username, AutofillHints.email],
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(labelText: 'Email or username'),
              ),
              const SizedBox(height: 12),
              TextField(
                key: const Key('password'),
                controller: _password,
                obscureText: _obscure,
                autofillHints: const [AutofillHints.password],
                decoration: InputDecoration(
                  labelText: 'Password',
                  suffixIcon: IconButton(
                    tooltip: _obscure ? 'Show password' : 'Hide password',
                    icon: Icon(
                      _obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                    ),
                    onPressed: () => setState(() => _obscure = !_obscure),
                  ),
                ),
                onSubmitted: (_) => _submit(),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),
        FilledButton(
          key: const Key('sign-in'),
          onPressed: _busy ? null : _submit,
          child: Text(_busy ? 'Signing in…' : 'Sign in'),
        ),
        const SizedBox(height: 12),
        Text(
          'Forgot your password or new here? Use the web dashboard to reset it or create a '
          'workspace.',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.bodySmall,
        ),
      ],
    );
  }
}

class ChangePasswordScreen extends StatefulWidget {
  const ChangePasswordScreen({super.key, required this.session});

  final Session session;

  @override
  State<ChangePasswordScreen> createState() => _ChangePasswordScreenState();
}

class _ChangePasswordScreenState extends State<ChangePasswordScreen> {
  final _current = TextEditingController();
  final _next = TextEditingController();
  final _confirm = TextEditingController();
  String? _error;
  bool _busy = false;

  Future<void> _submit() async {
    if (_next.text != _confirm.text) {
      setState(() => _error = "The new passwords don't match.");
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await widget.session.changePassword(_current.text, _next.text);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return _AuthScaffold(
      title: 'Choose a new password',
      subtitle:
          'Your account has a temporary password. Choose your own before continuing: at least '
          '12 characters, not one used elsewhere.',
      children: [
        if (_error != null) _ErrorBox(_error!),
        TextField(
          controller: _current,
          obscureText: true,
          decoration: const InputDecoration(labelText: 'Current password'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _next,
          obscureText: true,
          autofillHints: const [AutofillHints.newPassword],
          decoration: const InputDecoration(labelText: 'New password'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _confirm,
          obscureText: true,
          decoration: const InputDecoration(labelText: 'Confirm new password'),
          onSubmitted: (_) => _submit(),
        ),
        const SizedBox(height: 20),
        FilledButton(
          onPressed: _busy ? null : _submit,
          child: Text(_busy ? 'Saving…' : 'Save password'),
        ),
        TextButton(onPressed: widget.session.signOut, child: const Text('Sign out')),
      ],
    );
  }
}

/// Signed in, but no workspace has been chosen (or the person has none).
class OrganisationPicker extends StatelessWidget {
  const OrganisationPicker({super.key, required this.session});

  final Session session;

  @override
  Widget build(BuildContext context) {
    final memberships = session.me?.memberships ?? const [];
    return _AuthScaffold(
      title: memberships.isEmpty ? 'No workspace yet' : 'Choose a workspace',
      subtitle: memberships.isEmpty
          ? 'Create your business workspace on the web dashboard, or ask your administrator to '
                'invite you. Then come back here.'
          : 'You belong to more than one organisation.',
      children: [
        for (final m in memberships)
          Card(
            child: ListTile(
              title: Text(m.organisationName),
              subtitle: Text(m.roleLabel),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => session.selectOrganisation(m.organisationId),
            ),
          ),
        if (memberships.isEmpty)
          FilledButton.tonal(onPressed: session.refreshMe, child: const Text('Check again')),
        const SizedBox(height: 8),
        TextButton(onPressed: session.signOut, child: const Text('Sign out')),
      ],
    );
  }
}

/// The organisation requires MFA but this account has none yet.
class MfaRequiredScreen extends StatelessWidget {
  const MfaRequiredScreen({super.key, required this.session});

  final Session session;

  @override
  Widget build(BuildContext context) => _AuthScaffold(
    title: 'Two-step sign-in required',
    subtitle:
        '${session.membership?.organisationName ?? 'Your organisation'} requires two-step '
        'sign-in. Set it up on the web dashboard under Settings → Security, then sign in again.',
    children: [FilledButton.tonal(onPressed: session.signOut, child: const Text('Sign out'))],
  );
}

class LockScreen extends StatefulWidget {
  const LockScreen({super.key, required this.lock});

  final AppLock lock;

  @override
  State<LockScreen> createState() => _LockScreenState();
}

class _LockScreenState extends State<LockScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => widget.lock.unlock());
  }

  @override
  Widget build(BuildContext context) => _AuthScaffold(
    title: 'Locked',
    subtitle: 'Unlock with Face ID, fingerprint or your phone passcode.',
    children: [
      FilledButton.icon(
        onPressed: widget.lock.unlock,
        icon: const Icon(Icons.lock_open),
        label: const Text('Unlock'),
      ),
    ],
  );
}
