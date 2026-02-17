// ContactIQ Dark Intelligence Theme
// Professional surveillance interface aesthetic

export const colors = {
  // Primary Colors - Matrix Green with Cyan accents
  primary: '#00FF88',        // Bright intelligence green
  primaryVariant: '#00CC6A', // Darker green
  secondary: '#00FFFF',      // Cyan accent
  secondaryVariant: '#00CCCC',
  
  // Background Colors - Deep dark with subtle gradients
  background: '#0A0A0F',     // Deep space black
  backgroundVariant: '#12121A', // Slightly lighter
  surface: '#1A1A24',        // Card/panel background
  surfaceVariant: '#222230', // Elevated surface
  
  // Text Colors - High contrast for readability
  text: '#FFFFFF',           // Primary text
  textSecondary: '#B8B8C4',  // Secondary text
  textTertiary: '#6A6A78',   // Tertiary/hint text
  textOnPrimary: '#000000',  // Text on primary color
  
  // Status Colors
  success: '#00FF88',        // Success (same as primary)
  warning: '#FFB800',        // Warning amber
  error: '#FF3366',          // Error red
  info: '#00AAFF',           // Info blue
  
  // Border & Divider Colors
  border: '#2A2A38',         // Subtle borders
  divider: '#333344',        // Section dividers
  
  // Special Intelligence Colors
  data: '#00FFFF',           // Data highlighting (cyan)
  code: '#FF6B35',           // Code/technical data (orange)
  secure: '#00FF88',         // Security indicators (green)
  alert: '#FF3366',          // Alert indicators (red)
  
  // Glassmorphism
  glass: 'rgba(26, 26, 36, 0.8)',     // Semi-transparent surface
  glassBlur: 'rgba(255, 255, 255, 0.05)', // Light glass tint
};

export const fonts = {
  // Monospace fonts for data/code
  mono: {
    regular: 'JetBrainsMono-Regular',
    bold: 'JetBrainsMono-Bold',
  },
  
  // Sans-serif fonts for UI
  regular: 'Inter-Regular',
  medium: 'Inter-Medium',
  bold: 'Inter-Bold',
  
  // Font sizes
  sizes: {
    tiny: 10,
    small: 12,
    body: 14,
    subtitle: 16,
    title: 18,
    heading: 24,
    display: 32,
  },
};

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
};

export const borderRadius = {
  sm: 4,
  md: 8,
  lg: 16,
  xl: 24,
  full: 9999,
};

export const shadows = {
  sm: {
    shadowColor: colors.primary,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  
  md: {
    shadowColor: colors.primary,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.15,
    shadowRadius: 4,
    elevation: 4,
  },
  
  lg: {
    shadowColor: colors.primary,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 8,
  },
  
  glow: {
    shadowColor: colors.primary,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.3,
    shadowRadius: 10,
    elevation: 10,
  },
};

// Animation durations
export const animations = {
  fast: 200,
  normal: 300,
  slow: 500,
  
  // Easing curves
  easeInOut: 'ease-in-out',
  easeOut: 'ease-out',
  spring: 'spring',
};

// Component-specific styles
export const components = {
  card: {
    backgroundColor: colors.surface,
    borderRadius: borderRadius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadows.md,
  },
  
  button: {
    primary: {
      backgroundColor: colors.primary,
      borderRadius: borderRadius.md,
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.md,
      ...shadows.sm,
    },
    
    secondary: {
      backgroundColor: 'transparent',
      borderWidth: 1,
      borderColor: colors.border,
      borderRadius: borderRadius.md,
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.md,
    },
    
    ghost: {
      backgroundColor: 'transparent',
      borderRadius: borderRadius.md,
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.md,
    },
  },
  
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: borderRadius.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    fontSize: fonts.sizes.body,
    color: colors.text,
    fontFamily: fonts.regular,
  },
  
  // Intelligence-specific components
  dataDisplay: {
    backgroundColor: colors.glass,
    borderWidth: 1,
    borderColor: colors.data,
    borderRadius: borderRadius.sm,
    padding: spacing.sm,
    fontFamily: fonts.mono.regular,
    fontSize: fonts.sizes.small,
    color: colors.data,
  },
  
  statusIndicator: {
    online: {
      backgroundColor: colors.success,
      borderRadius: borderRadius.full,
      width: 8,
      height: 8,
      ...shadows.glow,
    },
    
    offline: {
      backgroundColor: colors.textTertiary,
      borderRadius: borderRadius.full,
      width: 8,
      height: 8,
    },
  },
};

// Navigation theme for React Navigation
export const navigation = {
  dark: true,
  colors: {
    primary: colors.primary,
    background: colors.background,
    card: colors.surface,
    text: colors.text,
    border: colors.border,
    notification: colors.error,
  },
};

// Export everything as default theme object
export const theme = {
  colors,
  fonts,
  spacing,
  borderRadius,
  shadows,
  animations,
  components,
  navigation,
};

export default theme;

// Utility functions for theme usage
export const getTextColor = (background) => {
  // Simple contrast calculation
  const isLight = background === colors.primary || background === colors.secondary;
  return isLight ? colors.textOnPrimary : colors.text;
};

export const getStatusColor = (status) => {
  const statusMap = {
    success: colors.success,
    warning: colors.warning,
    error: colors.error,
    info: colors.info,
    online: colors.success,
    offline: colors.textTertiary,
    pending: colors.warning,
    verified: colors.success,
    unverified: colors.error,
  };
  
  return statusMap[status] || colors.textSecondary;
};

export const createGlowEffect = (color = colors.primary, intensity = 0.3) => ({
  shadowColor: color,
  shadowOffset: { width: 0, height: 0 },
  shadowOpacity: intensity,
  shadowRadius: 8,
  elevation: 8,
});
