import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from '../store';
import * as ticketApi from '../../api/ticketApi';
import type {
  TicketListItem,
  TicketDetail,
  TicketMessageItem,
  AdminTicketListItem,
  PaginatedTickets,
  PaginatedAdminTickets,
  TicketDetailResponse,
  TicketStatusChangeResponse,
  AdminOpenCountResponse,
  CreateTicketPayload,
  SendTicketMessagePayload,
  TicketStatus,
  TicketCategory,
} from '../../types/ticket';
import axios from 'axios';

// --- State ---

interface PaginationInfo {
  page: number;
  totalPages: number;
}

export interface TicketState {
  // User view
  tickets: TicketListItem[];
  ticketsPagination: PaginationInfo;
  activeTicket: TicketDetail | null;
  messages: TicketMessageItem[];
  messagesPagination: PaginationInfo;
  // Admin view
  adminTickets: AdminTicketListItem[];
  adminTicketsPagination: PaginationInfo;
  adminOpenCount: number;
  // Common
  isLoading: boolean;
  error: string | null;
}

const initialState: TicketState = {
  tickets: [],
  ticketsPagination: { page: 1, totalPages: 1 },
  activeTicket: null,
  messages: [],
  messagesPagination: { page: 1, totalPages: 1 },
  adminTickets: [],
  adminTicketsPagination: { page: 1, totalPages: 1 },
  adminOpenCount: 0,
  isLoading: false,
  error: null,
};

// --- Async Thunks ---

export const fetchMyTickets = createAsyncThunk<
  PaginatedTickets,
  { page?: number; status?: TicketStatus } | void,
  { rejectValue: string }
>(
  'tickets/fetchMyTickets',
  async (params, thunkAPI) => {
    try {
      const response = await ticketApi.getMyTickets(params ?? {});
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось загрузить тикеты');
    }
  },
);

export const createTicket = createAsyncThunk<
  TicketListItem,
  CreateTicketPayload,
  { rejectValue: string }
>(
  'tickets/createTicket',
  async (data, thunkAPI) => {
    try {
      const response = await ticketApi.createTicket(data);
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 429) {
          return thunkAPI.rejectWithValue('Слишком много тикетов. Подождите немного.');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось создать тикет');
    }
  },
);

export const fetchTicketDetail = createAsyncThunk<
  TicketDetailResponse,
  { ticketId: number; page?: number; page_size?: number },
  { rejectValue: string }
>(
  'tickets/fetchTicketDetail',
  async ({ ticketId, page, page_size }, thunkAPI) => {
    try {
      const response = await ticketApi.getTicketDetail(ticketId, { page, page_size });
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 403) {
          return thunkAPI.rejectWithValue('У вас нет доступа к этому тикету');
        }
        if (error.response?.status === 404) {
          return thunkAPI.rejectWithValue('Тикет не найден');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось загрузить тикет');
    }
  },
);

export const sendTicketMessage = createAsyncThunk<
  TicketMessageItem,
  { ticketId: number; data: SendTicketMessagePayload },
  { rejectValue: string }
>(
  'tickets/sendTicketMessage',
  async ({ ticketId, data }, thunkAPI) => {
    try {
      const response = await ticketApi.sendTicketMessage(ticketId, data);
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        if (error.response?.status === 400) {
          return thunkAPI.rejectWithValue(
            error.response.data?.detail ?? 'Тикет закрыт, отправка сообщений невозможна',
          );
        }
        if (error.response?.status === 429) {
          return thunkAPI.rejectWithValue('Слишком частые сообщения. Подождите.');
        }
        if (error.response?.data?.detail) {
          return thunkAPI.rejectWithValue(error.response.data.detail);
        }
      }
      return thunkAPI.rejectWithValue('Не удалось отправить сообщение');
    }
  },
);

export const changeTicketStatus = createAsyncThunk<
  TicketStatusChangeResponse,
  { ticketId: number; status: TicketStatus },
  { rejectValue: string }
>(
  'tickets/changeTicketStatus',
  async ({ ticketId, status }, thunkAPI) => {
    try {
      const response = await ticketApi.changeTicketStatus(ticketId, status);
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось изменить статус тикета');
    }
  },
);

export const fetchAdminTickets = createAsyncThunk<
  PaginatedAdminTickets,
  { page?: number; status?: TicketStatus; category?: TicketCategory } | void,
  { rejectValue: string }
>(
  'tickets/fetchAdminTickets',
  async (params, thunkAPI) => {
    try {
      const response = await ticketApi.getAdminTickets(params ?? {});
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось загрузить список тикетов');
    }
  },
);

export const fetchAdminOpenCount = createAsyncThunk<
  AdminOpenCountResponse,
  void,
  { rejectValue: string }
>(
  'tickets/fetchAdminOpenCount',
  async (_, thunkAPI) => {
    try {
      const response = await ticketApi.getAdminOpenCount();
      return response.data;
    } catch (error: unknown) {
      if (axios.isAxiosError(error) && error.response?.data?.detail) {
        return thunkAPI.rejectWithValue(error.response.data.detail);
      }
      return thunkAPI.rejectWithValue('Не удалось загрузить счётчик тикетов');
    }
  },
);

// --- Slice ---

const ticketSlice = createSlice({
  name: 'tickets',
  initialState,
  reducers: {
    /** Handle WS ticket_reply — admin replied to user's ticket */
    receiveTicketReply(state, action: PayloadAction<{ ticket_id: number }>) {
      const { ticket_id } = action.payload;
      // Update ticket in user's list if present
      const ticket = state.tickets.find((t) => t.id === ticket_id);
      if (ticket) {
        ticket.status = 'awaiting_reply';
        ticket.updated_at = new Date().toISOString();
      }
      // If viewing this ticket, update active ticket status
      if (state.activeTicket?.id === ticket_id) {
        state.activeTicket.status = 'awaiting_reply';
        state.activeTicket.updated_at = new Date().toISOString();
      }
    },

    /** Handle WS ticket_new_message — new message from user (admin view) */
    receiveTicketNewMessage(state, action: PayloadAction<{ ticket_id: number }>) {
      const { ticket_id } = action.payload;
      // Update ticket in admin's list if present
      const ticket = state.adminTickets.find((t) => t.id === ticket_id);
      if (ticket) {
        ticket.updated_at = new Date().toISOString();
      }
    },

    clearTicketDetail(state) {
      state.activeTicket = null;
      state.messages = [];
      state.messagesPagination = { page: 1, totalPages: 1 };
    },

    clearTicketError(state) {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // fetchMyTickets
      .addCase(fetchMyTickets.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchMyTickets.fulfilled, (state, action) => {
        const { items, total, page, page_size } = action.payload;
        state.tickets = items;
        state.ticketsPagination = {
          page,
          totalPages: Math.max(1, Math.ceil(total / page_size)),
        };
        state.isLoading = false;
      })
      .addCase(fetchMyTickets.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // createTicket
      .addCase(createTicket.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(createTicket.fulfilled, (state, action) => {
        state.isLoading = false;
        state.tickets.unshift(action.payload);
      })
      .addCase(createTicket.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // fetchTicketDetail
      .addCase(fetchTicketDetail.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchTicketDetail.fulfilled, (state, action) => {
        const { ticket, messages: msgData } = action.payload;
        state.activeTicket = ticket;
        state.messages = msgData.items;
        state.messagesPagination = {
          page: msgData.page,
          totalPages: Math.max(1, Math.ceil(msgData.total / msgData.page_size)),
        };
        state.isLoading = false;
      })
      .addCase(fetchTicketDetail.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // sendTicketMessage
      .addCase(sendTicketMessage.pending, (state) => {
        state.error = null;
      })
      .addCase(sendTicketMessage.fulfilled, (state, action) => {
        state.messages.push(action.payload);
      })
      .addCase(sendTicketMessage.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // changeTicketStatus
      .addCase(changeTicketStatus.pending, (state) => {
        state.error = null;
      })
      .addCase(changeTicketStatus.fulfilled, (state, action) => {
        const { id, status, closed_at, closed_by } = action.payload;
        if (state.activeTicket?.id === id) {
          state.activeTicket.status = status;
          state.activeTicket.closed_at = closed_at;
          state.activeTicket.closed_by = closed_by;
        }
        // Update in admin list
        const adminTicket = state.adminTickets.find((t) => t.id === id);
        if (adminTicket) {
          adminTicket.status = status;
          adminTicket.closed_at = closed_at;
          adminTicket.closed_by = closed_by;
        }
        // Update in user list
        const userTicket = state.tickets.find((t) => t.id === id);
        if (userTicket) {
          userTicket.status = status;
          userTicket.closed_at = closed_at;
          userTicket.closed_by = closed_by;
        }
      })
      .addCase(changeTicketStatus.rejected, (state, action) => {
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // fetchAdminTickets
      .addCase(fetchAdminTickets.pending, (state) => {
        state.isLoading = true;
        state.error = null;
      })
      .addCase(fetchAdminTickets.fulfilled, (state, action) => {
        const { items, total, page, page_size } = action.payload;
        state.adminTickets = items;
        state.adminTicketsPagination = {
          page,
          totalPages: Math.max(1, Math.ceil(total / page_size)),
        };
        state.isLoading = false;
      })
      .addCase(fetchAdminTickets.rejected, (state, action) => {
        state.isLoading = false;
        state.error = action.payload ?? 'Произошла ошибка';
      })

      // fetchAdminOpenCount
      .addCase(fetchAdminOpenCount.fulfilled, (state, action) => {
        state.adminOpenCount = action.payload.open_count;
      })
      .addCase(fetchAdminOpenCount.rejected, () => {
        // Silent — non-critical for badge count
      });
  },
});

export const {
  receiveTicketReply,
  receiveTicketNewMessage,
  clearTicketDetail,
  clearTicketError,
} = ticketSlice.actions;

// --- Selectors ---

export const selectTickets = (state: RootState) => state.tickets.tickets;
export const selectTicketsPagination = (state: RootState) => state.tickets.ticketsPagination;
export const selectActiveTicket = (state: RootState) => state.tickets.activeTicket;
export const selectTicketMessages = (state: RootState) => state.tickets.messages;
export const selectTicketMessagesPagination = (state: RootState) => state.tickets.messagesPagination;
export const selectAdminTickets = (state: RootState) => state.tickets.adminTickets;
export const selectAdminTicketsPagination = (state: RootState) => state.tickets.adminTicketsPagination;
export const selectAdminOpenCount = (state: RootState) => state.tickets.adminOpenCount;
export const selectTicketsLoading = (state: RootState) => state.tickets.isLoading;
export const selectTicketsError = (state: RootState) => state.tickets.error;

export default ticketSlice.reducer;
