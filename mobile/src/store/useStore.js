import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';

// Main application store
export const useStore = create(
  persist(
    (set, get) => ({
      // Authentication state
      user: null,
      apiKey: null,
      isAuthenticated: false,
      authToken: null,

      // Dashboard data
      dashboardData: {
        stats: {
          totalContacts: 0,
          osintQueries: 0,
          callerIdQueries: 0,
          threatLevel: 'LOW',
        },
        recentContacts: [],
        alerts: [],
        osintHistory: [],
        lastUpdated: null,
      },

      // Contacts state
      contacts: {
        list: [],
        searchQuery: '',
        filters: {
          source: 'all',
          enrichmentStatus: 'all',
          dateRange: '7days',
        },
        pagination: {
          page: 1,
          limit: 50,
          total: 0,
        },
        selectedContact: null,
      },

      // Caller ID state
      callerIdHistory: [],
      currentCallerId: null,
      callerIdSettings: {
        enableRealTime: true,
        enableSpamDetection: true,
        autoBlock: false,
        confidenceThreshold: 0.7,
      },

      // OSINT state
      osint: {
        activeInvestigations: [],
        history: [],
        favorites: [],
        tools: {
          sherlock: { enabled: true, lastUsed: null },
          theHarvester: { enabled: true, lastUsed: null },
          holehe: { enabled: true, lastUsed: null },
          subfinder: { enabled: true, lastUsed: null },
          phoneinfoga: { enabled: true, lastUsed: null },
        },
        settings: {
          saveHistory: true,
          timeout: 120, // seconds
          maxConcurrent: 3,
        },
      },

      // QR Card state
      qrCards: {
        personal: null,
        saved: [],
        scannedHistory: [],
      },

      // Alerts state
      alerts: {
        list: [],
        unreadCount: 0,
        filters: {
          type: 'all',
          severity: 'all',
          read: 'unread',
        },
      },

      // App settings
      settings: {
        theme: 'dark',
        notifications: {
          enabled: true,
          alerts: true,
          osintComplete: true,
          newContacts: false,
        },
        privacy: {
          saveHistory: true,
          anonymousUsage: false,
          biometricAuth: false,
        },
        sync: {
          autoSync: true,
          syncInterval: 300, // 5 minutes
          lastSync: null,
        },
      },

      // UI state
      ui: {
        currentScreen: 'Dashboard',
        loading: false,
        error: null,
        toast: null,
        modal: null,
      },

      // Actions - Authentication
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      setApiKey: (apiKey) => set({ apiKey }),
      setAuthToken: (authToken) => set({ authToken }),
      
      login: (userData) => set({ 
        user: userData.user,
        apiKey: userData.api_key,
        authToken: userData.access_token,
        isAuthenticated: true,
      }),
      
      logout: () => set({ 
        user: null,
        apiKey: null,
        authToken: null,
        isAuthenticated: false,
      }),

      // Actions - Dashboard
      setDashboardData: (data) => set({ 
        dashboardData: { ...get().dashboardData, ...data } 
      }),
      
      updateStats: (stats) => set((state) => ({
        dashboardData: {
          ...state.dashboardData,
          stats: { ...state.dashboardData.stats, ...stats }
        }
      })),

      // Actions - Contacts
      setContacts: (contacts) => set((state) => ({
        contacts: { ...state.contacts, list: contacts }
      })),
      
      addContact: (contact) => set((state) => ({
        contacts: {
          ...state.contacts,
          list: [contact, ...state.contacts.list]
        }
      })),
      
      updateContact: (contactId, updates) => set((state) => ({
        contacts: {
          ...state.contacts,
          list: state.contacts.list.map(contact =>
            contact.id === contactId ? { ...contact, ...updates } : contact
          )
        }
      })),
      
      deleteContact: (contactId) => set((state) => ({
        contacts: {
          ...state.contacts,
          list: state.contacts.list.filter(contact => contact.id !== contactId)
        }
      })),
      
      setContactsSearchQuery: (query) => set((state) => ({
        contacts: { ...state.contacts, searchQuery: query }
      })),
      
      setContactsFilters: (filters) => set((state) => ({
        contacts: { 
          ...state.contacts, 
          filters: { ...state.contacts.filters, ...filters }
        }
      })),
      
      setSelectedContact: (contact) => set((state) => ({
        contacts: { ...state.contacts, selectedContact: contact }
      })),

      // Actions - Caller ID
      addCallerIdResult: (result) => set((state) => ({
        callerIdHistory: [result, ...state.callerIdHistory.slice(0, 99)] // Keep last 100
      })),
      
      setCurrentCallerId: (callerId) => set({ currentCallerId: callerId }),
      
      updateCallerIdSettings: (settings) => set((state) => ({
        callerIdSettings: { ...state.callerIdSettings, ...settings }
      })),

      // Actions - OSINT
      addOSINTInvestigation: (investigation) => set((state) => ({
        osint: {
          ...state.osint,
          activeInvestigations: [investigation, ...state.osint.activeInvestigations],
        }
      })),
      
      updateOSINTInvestigation: (id, updates) => set((state) => ({
        osint: {
          ...state.osint,
          activeInvestigations: state.osint.activeInvestigations.map(inv =>
            inv.id === id ? { ...inv, ...updates } : inv
          )
        }
      })),
      
      completeOSINTInvestigation: (id, results) => set((state) => {
        const investigation = state.osint.activeInvestigations.find(inv => inv.id === id);
        if (!investigation) return state;
        
        const completedInvestigation = {
          ...investigation,
          ...results,
          status: 'completed',
          completedAt: new Date().toISOString(),
        };
        
        return {
          osint: {
            ...state.osint,
            activeInvestigations: state.osint.activeInvestigations.filter(inv => inv.id !== id),
            history: [completedInvestigation, ...state.osint.history.slice(0, 99)],
          }
        };
      }),
      
      toggleOSINTTool: (tool) => set((state) => ({
        osint: {
          ...state.osint,
          tools: {
            ...state.osint.tools,
            [tool]: {
              ...state.osint.tools[tool],
              enabled: !state.osint.tools[tool].enabled
            }
          }
        }
      })),
      
      updateOSINTSettings: (settings) => set((state) => ({
        osint: {
          ...state.osint,
          settings: { ...state.osint.settings, ...settings }
        }
      })),

      // Actions - QR Cards
      setPersonalQRCard: (card) => set((state) => ({
        qrCards: { ...state.qrCards, personal: card }
      })),
      
      addSavedQRCard: (card) => set((state) => ({
        qrCards: {
          ...state.qrCards,
          saved: [card, ...state.qrCards.saved]
        }
      })),
      
      addScannedQRCard: (card) => set((state) => ({
        qrCards: {
          ...state.qrCards,
          scannedHistory: [card, ...state.qrCards.scannedHistory.slice(0, 49)]
        }
      })),

      // Actions - Alerts
      setAlerts: (alerts) => set((state) => ({
        alerts: { 
          ...state.alerts, 
          list: alerts,
          unreadCount: alerts.filter(alert => !alert.read).length
        }
      })),
      
      addAlert: (alert) => set((state) => ({
        alerts: {
          ...state.alerts,
          list: [alert, ...state.alerts.list],
          unreadCount: state.alerts.unreadCount + (alert.read ? 0 : 1)
        }
      })),
      
      markAlertAsRead: (alertId) => set((state) => ({
        alerts: {
          ...state.alerts,
          list: state.alerts.list.map(alert =>
            alert.id === alertId ? { ...alert, read: true } : alert
          ),
          unreadCount: Math.max(0, state.alerts.unreadCount - 1)
        }
      })),
      
      deleteAlert: (alertId) => set((state) => {
        const alert = state.alerts.list.find(a => a.id === alertId);
        return {
          alerts: {
            ...state.alerts,
            list: state.alerts.list.filter(a => a.id !== alertId),
            unreadCount: state.alerts.unreadCount - (alert && !alert.read ? 1 : 0)
          }
        };
      }),

      // Actions - Settings
      updateSettings: (settings) => set((state) => ({
        settings: { ...state.settings, ...settings }
      })),
      
      updateNotificationSettings: (notifications) => set((state) => ({
        settings: {
          ...state.settings,
          notifications: { ...state.settings.notifications, ...notifications }
        }
      })),
      
      updatePrivacySettings: (privacy) => set((state) => ({
        settings: {
          ...state.settings,
          privacy: { ...state.settings.privacy, ...privacy }
        }
      })),
      
      updateSyncSettings: (sync) => set((state) => ({
        settings: {
          ...state.settings,
          sync: { ...state.settings.sync, ...sync }
        }
      })),

      // Actions - UI
      setCurrentScreen: (screen) => set((state) => ({
        ui: { ...state.ui, currentScreen: screen }
      })),
      
      setLoading: (loading) => set((state) => ({
        ui: { ...state.ui, loading }
      })),
      
      setError: (error) => set((state) => ({
        ui: { ...state.ui, error }
      })),
      
      clearError: () => set((state) => ({
        ui: { ...state.ui, error: null }
      })),
      
      showToast: (toast) => set((state) => ({
        ui: { ...state.ui, toast }
      })),
      
      hideToast: () => set((state) => ({
        ui: { ...state.ui, toast: null }
      })),
      
      showModal: (modal) => set((state) => ({
        ui: { ...state.ui, modal }
      })),
      
      hideModal: () => set((state) => ({
        ui: { ...state.ui, modal: null }
      })),

      // Utility actions
      resetStore: () => set({
        user: null,
        apiKey: null,
        isAuthenticated: false,
        authToken: null,
        dashboardData: {
          stats: { totalContacts: 0, osintQueries: 0, callerIdQueries: 0, threatLevel: 'LOW' },
          recentContacts: [],
          alerts: [],
          osintHistory: [],
          lastUpdated: null,
        },
        contacts: {
          list: [],
          searchQuery: '',
          filters: { source: 'all', enrichmentStatus: 'all', dateRange: '7days' },
          pagination: { page: 1, limit: 50, total: 0 },
          selectedContact: null,
        },
        callerIdHistory: [],
        currentCallerId: null,
        osint: {
          activeInvestigations: [],
          history: [],
          favorites: [],
        },
        qrCards: { personal: null, saved: [], scannedHistory: [] },
        alerts: { list: [], unreadCount: 0 },
      }),
      
      // Get filtered/computed data
      getFilteredContacts: () => {
        const state = get();
        const { list, searchQuery, filters } = state.contacts;
        
        return list.filter(contact => {
          // Search filter
          if (searchQuery) {
            const query = searchQuery.toLowerCase();
            const matchesSearch = (
              contact.name?.toLowerCase().includes(query) ||
              contact.email?.toLowerCase().includes(query) ||
              contact.company?.toLowerCase().includes(query)
            );
            if (!matchesSearch) return false;
          }
          
          // Source filter
          if (filters.source !== 'all' && contact.source !== filters.source) {
            return false;
          }
          
          // Enrichment status filter
          if (filters.enrichmentStatus !== 'all') {
            const hasEnrichedData = contact.enriched_data && 
              Object.keys(JSON.parse(contact.enriched_data)).length > 0;
            
            if (filters.enrichmentStatus === 'enriched' && !hasEnrichedData) return false;
            if (filters.enrichmentStatus === 'not_enriched' && hasEnrichedData) return false;
          }
          
          // Date range filter
          if (filters.dateRange !== 'all') {
            const now = new Date();
            const contactDate = new Date(contact.created_at);
            const daysDiff = (now - contactDate) / (1000 * 60 * 60 * 24);
            
            switch (filters.dateRange) {
              case '7days':
                if (daysDiff > 7) return false;
                break;
              case '30days':
                if (daysDiff > 30) return false;
                break;
              case '90days':
                if (daysDiff > 90) return false;
                break;
            }
          }
          
          return true;
        });
      },
      
      getUnreadAlertsCount: () => {
        const state = get();
        return state.alerts.list.filter(alert => !alert.read).length;
      },
      
      getActiveOSINTCount: () => {
        const state = get();
        return state.osint.activeInvestigations.length;
      },
      
      getEnabledOSINTTools: () => {
        const state = get();
        return Object.entries(state.osint.tools)
          .filter(([, tool]) => tool.enabled)
          .map(([name]) => name);
      },
    }),
    {
      name: 'contactiq-store',
      storage: createJSONStorage(() => AsyncStorage),
      
      // Exclude sensitive data from persistence
      partialize: (state) => ({
        user: state.user,
        settings: state.settings,
        qrCards: state.qrCards,
        callerIdSettings: state.callerIdSettings,
        osint: {
          ...state.osint,
          activeInvestigations: [], // Don't persist active investigations
        },
      }),
      
      // Rehydration callback
      onRehydrateStorage: () => (state) => {
        if (state) {
          console.log('Store rehydrated successfully');
        } else {
          console.log('Store rehydration failed');
        }
      },
    }
  )
);

// Selectors for better performance
export const useAuthState = () => useStore((state) => ({
  user: state.user,
  apiKey: state.apiKey,
  isAuthenticated: state.isAuthenticated,
  authToken: state.authToken,
}));

export const useDashboardData = () => useStore((state) => state.dashboardData);

export const useContactsState = () => useStore((state) => ({
  contacts: state.contacts,
  filteredContacts: state.getFilteredContacts(),
}));

export const useOSINTState = () => useStore((state) => ({
  osint: state.osint,
  activeCount: state.getActiveOSINTCount(),
  enabledTools: state.getEnabledOSINTTools(),
}));

export const useAlertsState = () => useStore((state) => ({
  alerts: state.alerts,
  unreadCount: state.getUnreadAlertsCount(),
}));

export const useUIState = () => useStore((state) => state.ui);

export const useAppSettings = () => useStore((state) => state.settings);

// Export default store
export default useStore;
