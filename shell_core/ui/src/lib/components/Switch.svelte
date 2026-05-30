<script>
  // Switch — the standard on/off toggle. Pill track + sliding knob; the
  // "on" state fills with the theme accent bar (same token as active-tab /
  // active-row), the "off" state is a faint glass track. Replaces native
  // checkboxes wherever a boolean toggle is shown.
  //
  // Mirrors GlassDropdown's callback shape: onChange receives the next value.
  let { checked = false, onChange, disabled = false, label = '' } = $props()

  function toggle() { if (!disabled) onChange?.(!checked) }
</script>

<button
  type="button"
  role="switch"
  aria-checked={checked}
  aria-label={label || undefined}
  {disabled}
  onclick={toggle}
  class="relative w-9 h-5 rounded-full shrink-0 transition disabled:opacity-40
         {checked ? '' : 'bg-white/10 hover:bg-white/[0.14]'}"
  style={checked ? 'background: var(--accent-bar);' : ''}
>
  <span
    class="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform
           {checked ? 'translate-x-4' : ''}"
  ></span>
</button>
