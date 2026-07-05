<script setup lang="ts">
import { defineComponent, h } from 'vue'

export const SettingsCheckboxMark = defineComponent({
  props: {
    checked: { type: Boolean, required: true },
    disabled: { type: Boolean, default: false },
  },
  setup(props) {
    return () => {
      const baseClass = 'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-all peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--color-brand)]/40'
      const checkedClass = props.checked
        ? 'border-[var(--color-brand)] bg-[var(--color-brand)] text-white shadow-[var(--shadow-button-primary)]'
        : 'border-[var(--color-border-focus)] bg-[var(--color-surface)] text-transparent'
      const disabledClass = props.disabled ? 'opacity-50' : ''
      return h(
        'span',
        {
          'aria-hidden': 'true',
          class: `${baseClass} ${checkedClass} ${disabledClass}`,
        },
        h('span', {
          class: 'material-symbols-outlined text-[16px] leading-none',
          style: { fontVariationSettings: "'FILL' 1" },
        }, 'check'),
      )
    }
  },
})
</script>